import json
from datetime import datetime
from Config.redis import redis_client
from Config.db import borrowers_collection, call_logs_collection
from services.intent_service import detect_intent
from services.escalation_service import should_escalate
from services.outcome_service import log_call_outcome
from bson import ObjectId
import re


CONVERSATION_TTL = 1800  # 30 minutes — clears Redis state after call ends


async def get_borrower(borrower_id: str) -> dict | None:
    """Fetch borrower from MongoDB by borrower_id or _id."""
    borrower = await borrowers_collection.find_one({"borrower_id": borrower_id})
    if not borrower:
        try:
            borrower = await borrowers_collection.find_one({"_id": ObjectId(borrower_id)})
        except Exception:
            pass
    if borrower:
        borrower["_id"] = str(borrower["_id"])
    return borrower


async def get_conversation_state(call_id: str) -> dict:
    """Load conversation state from Redis."""
    data = await redis_client.get(f"conv:{call_id}")
    if data:
        return json.loads(data)
    return {"turn": 0, "intent_history": [], "awaiting": None}


async def save_conversation_state(call_id: str, state: dict):
    """Persist conversation state to Redis with TTL."""
    await redis_client.setex(f"conv:{call_id}", CONVERSATION_TTL, json.dumps(state))


async def clear_conversation_state(call_id: str):
    """Delete Redis state when call ends."""
    await redis_client.delete(f"conv:{call_id}")


# ─── Opening message when call connects ───────────────────────────────────────

async def build_opening_message(borrower_id: str, call_id: str, language: str = "en") -> str:
    borrower = await get_borrower(borrower_id)
    if not borrower:
        return "Hello, this is a call regarding your loan account. Please contact us at your convenience."

    # Initialize Redis state
    state = {"turn": 0, "intent_history": [], "awaiting": "payment_intent", "language": language}
    await save_conversation_state(call_id, state)

    name = borrower.get("name", "Sir/Madam")
    amount = borrower.get("emi_amount", "")
    due_date = borrower.get("due_date", "")

    return (
        f"Hello, am I speaking with {name}? "
        f"This is a call from your lending institution regarding your EMI of "
        f"₹{amount} which was due on {due_date}. "
        f"Could you please let us know when you will be able to make this payment?"
    )

def extract_date_from_text(text: str) -> str:
    """Extract just the date portion from borrower's response."""
    
    # Match patterns like "15th June", "15 June", "June 15", "15/06", "15-06-2025"
    patterns = [
        r"\b(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?:\s+\d{4})?)\b",
        r"\b((?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+\d{4})?)\b",
        r"\b(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b",
        r"\b(next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b",
        r"\b(tomorrow)\b",
        r"\b(\d{1,2}(?:st|nd|rd|th)?)\b",  # just a number like "15th"
    ]
    
    text_lower = text.lower()
    for pattern in patterns:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            return match.group(1).strip().title()  # "15th June"
    
    # Fallback — return as-is if no date pattern found
    return text

# ─── Core conversation processing ─────────────────────────────────────────────

async def process_conversation(borrower_id: str, text: str, call_id: str) -> dict:
    """
    Process one turn of conversation.
    Returns dict: { response: str, action: str }
    action values: "continue" | "escalate" | "end_call"
    """
    borrower = await get_borrower(borrower_id)
    state = await get_conversation_state(call_id)

    intent, confidence = detect_intent(text)
    state["turn"] += 1
    state["intent_history"].append(intent)

    # ── Escalation check first ─────────────────────────────────────────────────
    if should_escalate(intent):
        await log_call_outcome({
            "borrower_id": borrower_id,
            "call_id": call_id,
            "intent": intent,
            "outcome": "ESCALATED",
            "commitment_date": None,
            "commitment_amount": None
        })
        await clear_conversation_state(call_id)
        return {
            "response": (
                "I completely understand your situation. "
                "Let me connect you with one of our senior support officers "
                "who can assist you better. Please hold."
            ),
            "action": "escalate"
        }

    

    # ── If bot was waiting for a date, treat ANY response as the date ─────────
    if state.get("awaiting") == "commitment_date":
        extracted_date = extract_date_from_text(text)   # ← extract clean date
        state["commitment_date"] = extracted_date
        state["awaiting"] = None
        await save_conversation_state(call_id, state)
        amount = borrower.get("emi_amount") if borrower else "the outstanding amount"
        await log_call_outcome({
            "borrower_id": borrower_id,
            "call_id": call_id,
            "intent": "PAY_LATER",
            "outcome": "COMMITTED",
            "commitment_date": extracted_date,          # ← clean date in DB too
            "commitment_amount": amount
        })
        return {
            "response": (
                f"Thank you. We've noted your commitment to pay ₹{amount} by {extracted_date}. "
                "We'll send you a reminder before the date. Have a good day!"
            ),
            "action": "end_call"
        }

    # ── Intent routing ─────────────────────────────────────────────────────────

    if intent == "PAY_NOW":
        amount = borrower.get("emi_amount") if borrower else "the outstanding"
        await log_call_outcome({
            "borrower_id": borrower_id,
            "call_id": call_id,
            "intent": intent,
            "outcome": "COMMITTED",
            "commitment_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "commitment_amount": amount
        })
        await clear_conversation_state(call_id)
        return {
            "response": (
                f"Thank you so much! Please make the payment of ₹{amount} today. "
                "You can pay via UPI, NEFT, or your bank's net banking. "
                "We appreciate your cooperation. Have a good day!"
            ),
            "action": "end_call"
        }

    if intent == "PAY_LATER":
        state["awaiting"] = "commitment_date"
        await save_conversation_state(call_id, state)
        return {
            "response": (
                "I understand. Could you please confirm the exact date "
                "by which you will make the payment? "
                "This will help us update your account."
            ),
            "action": "continue"
        }

    if intent == "CONFIRM_DATE":
        state["commitment_date"] = text
        state["awaiting"] = None
        await save_conversation_state(call_id, state)
        amount = borrower.get("emi_amount") if borrower else "the outstanding amount"
        await log_call_outcome({
            "borrower_id": borrower_id,
            "call_id": call_id,
            "intent": "PAY_LATER",
            "outcome": "COMMITTED",
            "commitment_date": text,
            "commitment_amount": amount
        })
        return {
            "response": (
                f"Thank you. We've noted your commitment to pay ₹{amount} by {text}. "
                "We'll send you a reminder before the date. Have a good day!"
            ),
            "action": "end_call"
        }

    if intent == "CALLBACK_REQUESTED":
        state["awaiting"] = "callback_time"
        await save_conversation_state(call_id, state)
        await log_call_outcome({
            "borrower_id": borrower_id,
            "call_id": call_id,
            "intent": intent,
            "outcome": "CALLBACK_REQUESTED",
            "commitment_date": None,
            "commitment_amount": None
        })
        return {
            "response": (
                "Of course, I understand. "
                "What time would be convenient for us to call you back?"
            ),
            "action": "continue"
        }

    if intent == "WRONG_NUMBER":
        await log_call_outcome({
            "borrower_id": borrower_id,
            "call_id": call_id,
            "intent": intent,
            "outcome": "WRONG_NUMBER",
            "commitment_date": None,
            "commitment_amount": None
        })
        await clear_conversation_state(call_id)
        return {
            "response": (
                "We apologize for the inconvenience. "
                "We will update our records. Have a good day!"
            ),
            "action": "end_call"
        }

    if intent == "DISPUTE":
        await log_call_outcome({
            "borrower_id": borrower_id,
            "call_id": call_id,
            "intent": intent,
            "outcome": "ESCALATED",
            "commitment_date": None,
            "commitment_amount": None
        })
        await clear_conversation_state(call_id)
        return {
            "response": (
                "I understand you have a dispute regarding this account. "
                "I'm transferring you to our dispute resolution team. Please hold."
            ),
            "action": "escalate"
        }

    # ── Awaiting-specific follow-ups ───────────────────────────────────────────

    if state.get("awaiting") == "payment_intent":
        # Borrower said something unrecognized on first turn — re-prompt
        return {
            "response": (
                "I'm sorry, I didn't quite catch that. "
                "Could you let me know when you'd be able to make your EMI payment?"
            ),
            "action": "continue"
        }

    # ── Fallback ───────────────────────────────────────────────────────────────
    await save_conversation_state(call_id, state)
    return {
        "response": (
            "I understand. To help you better, could you please confirm "
            "when you'll be able to make the payment?"
        ),
        "action": "continue"
    }