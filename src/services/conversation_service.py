import json
from datetime import datetime
from Config.redis import redis_client
from Config.db import borrowers_collection, call_logs_collection
from services.intent_service import detect_intent
from services.escalation_service import should_escalate
from services.outcome_service import log_call_outcome
from bson import ObjectId
import re


CONVERSATION_TTL = 1800  # 30 minutes


# ─── Bilingual response templates ─────────────────────────────────────────────

RESPONSES = {
    "en": {
        "emi_inform": (
            "I'm calling regarding your overdue EMI of ₹{amount} "
            "which was due on {due_date} and is {dpd} days overdue. "
            "When will you be able to make this payment?"
        ),
        "ask_date": (
            "I understand. Could you please confirm the exact date "
            "by which you will make the payment?"
        ),
        "committed": (
            "Thank you. We've noted your commitment to pay ₹{amount} by {date}. "
            "We'll send you a reminder. Have a good day!"
        ),
        "pay_now": (
            "Thank you! Please make the payment of ₹{amount} today via UPI or NEFT. "
            "We appreciate your cooperation. Have a good day!"
        ),
        "escalate": (
            "I understand your situation. Let me connect you with one of our "
            "senior support officers who can assist you better. Please hold."
        ),
        "wrong_number": (
            "We apologize for the inconvenience. "
            "We will update our records. Have a good day!"
        ),
        "callback": (
            "Of course. What time would be convenient for us to call you back?"
        ),
        "dispute": (
            "I understand you have a dispute. "
            "I'm transferring you to our dispute resolution team. Please hold."
        ),
        "fallback": (
            "Could you please confirm when you'll be able to make the payment?"
        ),
        "not_you": (
            "I apologize for the inconvenience. "
            "We will update our records. Have a good day!"
        ),
        "reprompt": (
            "I'm sorry, I didn't catch that. "
            "Could you let me know when you'd be able to make your EMI payment?"
        ),
    },
    "hi": {
        "emi_inform": (
            "Main aapke ₹{amount} ke overdue EMI ke baare mein call kar raha hoon, "
            "jo {due_date} ko due tha aur abhi {dpd} din se overdue hai. "
            "Aap yeh payment kab kar sakte hain?"
        ),
        "ask_date": (
            "Main samajhta hoon. Kya aap exact date bata sakte hain "
            "jab aap payment karenge?"
        ),
        "committed": (
            "Shukriya. Humne note kar liya hai ki aap ₹{amount} {date} tak bharenge. "
            "Hum aapko reminder bhejenge. Dhanyawaad!"
        ),
        "pay_now": (
            "Shukriya! Kripaya aaj ₹{amount} UPI ya NEFT se bhejein. "
            "Aapka sahyog ke liye dhanyawaad. Shubh din!"
        ),
        "escalate": (
            "Main aapki baat samajhta hoon. Main aapko hamare senior officer se "
            "connect karta hoon jo aapki madad kar sakenge. Kripaya rukein."
        ),
        "wrong_number": (
            "Maafi chahta hoon. Hum apne records update kar lenge. Dhanyawaad!"
        ),
        "callback": (
            "Bilkul. Aap kis waqt call receive kar sakte hain?"
        ),
        "dispute": (
            "Main samajhta hoon aapka dispute hai. "
            "Main aapko hamare dispute team se connect karta hoon. Kripaya rukein."
        ),
        "fallback": (
            "Kya aap bata sakte hain ki payment kab karenge?"
        ),
        "not_you": (
            "Maafi chahta hoon. Hum apne records update kar lenge. Dhanyawaad!"
        ),
        "reprompt": (
            "Maafi chahta hoon, main samajh nahi paya. "
            "Kya aap bata sakte hain ki EMI payment kab karenge?"
        ),
    }
}


def get_response(lang: str, key: str, **kwargs) -> str:
    """Get response in correct language with variable substitution."""
    lang = lang if lang in RESPONSES else "en"
    template = RESPONSES[lang].get(key, RESPONSES["en"].get(key, ""))
    return template.format(**kwargs) if kwargs else template


# ─── MongoDB helpers ───────────────────────────────────────────────────────────

async def get_borrower(borrower_id: str) -> dict | None:
    borrower = await borrowers_collection.find_one({"borrower_id": borrower_id})
    if not borrower:
        try:
            borrower = await borrowers_collection.find_one({"_id": ObjectId(borrower_id)})
        except Exception:
            pass
    if borrower:
        borrower["_id"] = str(borrower["_id"])
    return borrower


async def update_borrower_language(borrower_id: str, language: str):
    """Update borrower's language in MongoDB."""
    try:
        print(f"[LANG] Attempting to update borrower_id={borrower_id} to language={language}")
        result = await borrowers_collection.update_one(
            {"_id": ObjectId(borrower_id)},
            {"$set": {"language": language}}
        )
        print(f"[LANG] matched={result.matched_count} modified={result.modified_count}")
        if result.matched_count == 0:
            print(f"[LANG ERROR] No borrower found with _id={borrower_id}")
    except Exception as e:
        print(f"[LANG ERROR] Exception: {str(e)}")


# ─── Redis helpers ─────────────────────────────────────────────────────────────

async def get_conversation_state(call_id: str) -> dict:
    data = await redis_client.get(f"conv:{call_id}")
    if data:
        return json.loads(data)
    return {"turn": 0, "intent_history": [], "awaiting": None, "language": "en"}


async def save_conversation_state(call_id: str, state: dict):
    await redis_client.setex(f"conv:{call_id}", CONVERSATION_TTL, json.dumps(state))


async def clear_conversation_state(call_id: str):
    await redis_client.delete(f"conv:{call_id}")


# ─── Date extraction ───────────────────────────────────────────────────────────

def extract_date_from_text(text: str) -> str:
    patterns = [
        r"\b(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?:\s+\d{4})?)\b",
        r"\b((?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+\d{4})?)\b",
        r"\b(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b",
        r"\b(next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b",
        r"\b(tomorrow|kal)\b",
        r"\b(\d{1,2}(?:st|nd|rd|th)?)\b",
    ]
    text_lower = text.lower()
    for pattern in patterns:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            return match.group(1).strip().title()
    return text


# ─── Opening greeting (Step 1 — identity confirmation) ────────────────────────

async def build_opening_message(borrower_id: str, call_id: str, language: str = "en") -> str:
    borrower = await get_borrower(borrower_id)
    if not borrower:
        return "Hello, this is a call regarding your loan account. Please contact us."

    state = {
        "turn": 0,
        "intent_history": [],
        "awaiting": "identity_confirmation",
        "language": "en",
        "borrower_id": borrower_id
    }
    await save_conversation_state(call_id, state)

    name = borrower.get("name", "Sir/Madam")

    # Single greeting — asks identity AND language in one go
    return (
        f"Hello, I am a Loan Collection Agent. "
        f"Am I speaking with {name}? "
        f"Namaste, main ek Loan Collection Agent hoon. "
        f"Kya main {name} se baat kar rahi hoon? "
        f"Please say Yes for English, "
        f"ya Hindi mein baat karne ke liye Hindi boliye."
    )


# ─── Core conversation processing ─────────────────────────────────────────────

async def process_conversation(borrower_id: str, text: str, call_id: str) -> dict:
    borrower = await get_borrower(borrower_id)
    state = await get_conversation_state(call_id)
    lang = state.get("language", "en")

    intent, confidence = detect_intent(text)
    state["turn"] += 1
    state["intent_history"].append(intent)

    print(f"[CONV] Turn {state['turn']} | awaiting={state.get('awaiting')} | intent={intent} | lang={lang}")

    # ── STEP 1: Identity confirmation ──────────────────────────────────────────
    if state.get("awaiting") == "identity_confirmation":

     if intent == "LANG_HINDI" or "hindi" in text.lower():
        # Confirmed identity AND chose Hindi in one shot
        state["language"] = "hi"
        state["awaiting"] = "payment_intent"
        await save_conversation_state(call_id, state)
        await update_borrower_language(borrower_id, "hi")
        amount = borrower.get("emi_amount", "") if borrower else ""
        due_date = borrower.get("due_date", "") if borrower else ""
        dpd = borrower.get("days_past_due", "") if borrower else ""
        return {
            "response": get_response("hi", "emi_inform", amount=amount, due_date=due_date, dpd=dpd),
            "action": "continue"
        }

     elif intent in ("YES", "LANG_ENGLISH") or "english" in text.lower():
        # Confirmed identity — chose or defaulted to English
        state["language"] = "en"
        state["awaiting"] = "payment_intent"
        await save_conversation_state(call_id, state)
        await update_borrower_language(borrower_id, "en")
        amount = borrower.get("emi_amount", "") if borrower else ""
        due_date = borrower.get("due_date", "") if borrower else ""
        dpd = borrower.get("days_past_due", "") if borrower else ""
        return {
            "response": get_response("en", "emi_inform", amount=amount, due_date=due_date, dpd=dpd),
            "action": "continue"
        }

     elif intent in ("NO", "WRONG_NUMBER"):
        await log_call_outcome({
            "borrower_id": borrower_id,
            "call_id": call_id,
            "intent": "WRONG_NUMBER",
            "intent_history": state["intent_history"],
            "outcome": "WRONG_NUMBER",
        })
        await clear_conversation_state(call_id)
        return {
            "response": "We apologize for the inconvenience. Have a good day!",
            "action": "end_call"
        }

     else:
        # Re-ask
        name = borrower.get("name", "Sir/Madam") if borrower else "Sir/Madam"
        return {
            "response": (
                f"Am I speaking with {name}? "
                f"Say Yes for English, ya Hindi ke liye Hindi boliye. "
                f"Say No if wrong number."
            ),
            "action": "continue"
        }

    # ── STEP 2: Language selection ─────────────────────────────────────────────
    if state.get("awaiting") == "language_selection":

        text_lower = text.lower().strip()
        print(f"[LANG SELECT] text='{text}' intent={intent}")

        if intent == "LANG_HINDI" or "hindi" in text_lower:
            state["language"] = "hi"
            lang = "hi"
            state["awaiting"] = "payment_intent"
            await save_conversation_state(call_id, state)
            await update_borrower_language(borrower_id, language="hi")
            amount = borrower.get("emi_amount", "") if borrower else ""
            due_date = borrower.get("due_date", "") if borrower else ""
            dpd = borrower.get("days_past_due", "") if borrower else ""
            return {
                "response": get_response("hi", "emi_inform", amount=amount, due_date=due_date, dpd=dpd),
                "action": "continue"
            }

        elif intent == "LANG_ENGLISH" or "english" in text_lower:
            state["language"] = "en"
            lang = "en"
            state["awaiting"] = "payment_intent"
            await save_conversation_state(call_id, state)
            await update_borrower_language(borrower_id, language="en")
            amount = borrower.get("emi_amount", "") if borrower else ""
            due_date = borrower.get("due_date", "") if borrower else ""
            dpd = borrower.get("days_past_due", "") if borrower else ""
            return {
                "response": get_response("en", "emi_inform", amount=amount, due_date=due_date, dpd=dpd),
                "action": "continue"
            }

        else:
            return {
                "response": (
                    "Please say English for English, "
                    "ya Hindi ke liye Hindi boliye."
                ),
                "action": "continue"
            }

    # ── Escalation check ───────────────────────────────────────────────────────
    if should_escalate(intent):
        await log_call_outcome({
            "borrower_id": borrower_id,
            "call_id": call_id,
            "intent": intent,
            "intent_history": state["intent_history"],
            "outcome": "ESCALATED",
        })
        await clear_conversation_state(call_id)
        return {
            "response": get_response(lang, "escalate"),
            "action": "escalate"
        }

    # ── Awaiting commitment date ───────────────────────────────────────────────
    if state.get("awaiting") == "commitment_date":
        extracted_date = extract_date_from_text(text)
        state["commitment_date"] = extracted_date
        state["awaiting"] = None
        await save_conversation_state(call_id, state)
        amount = borrower.get("emi_amount", "the outstanding amount") if borrower else "the outstanding amount"
        await log_call_outcome({
            "borrower_id": borrower_id,
            "call_id": call_id,
            "intent": "PAY_LATER",
            "intent_history": state["intent_history"],
            "outcome": "COMMITTED",
            "commitment_date": extracted_date,
            "commitment_amount": amount,
        })
        return {
            "response": get_response(lang, "committed", amount=amount, date=extracted_date),
            "action": "end_call"
        }

    # ── Intent routing ─────────────────────────────────────────────────────────
    if intent == "PAY_NOW":
        amount = borrower.get("emi_amount", "the outstanding") if borrower else "the outstanding"
        await log_call_outcome({
            "borrower_id": borrower_id,
            "call_id": call_id,
            "intent": intent,
            "intent_history": state["intent_history"],
            "outcome": "COMMITTED",
            "commitment_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "commitment_amount": amount,
        })
        await clear_conversation_state(call_id)
        return {
            "response": get_response(lang, "pay_now", amount=amount),
            "action": "end_call"
        }

    if intent == "PAY_LATER":
        state["awaiting"] = "commitment_date"
        await save_conversation_state(call_id, state)
        return {
            "response": get_response(lang, "ask_date"),
            "action": "continue"
        }

    if intent == "CONFIRM_DATE":
        extracted_date = extract_date_from_text(text)
        state["commitment_date"] = extracted_date
        state["awaiting"] = None
        await save_conversation_state(call_id, state)
        amount = borrower.get("emi_amount", "the outstanding amount") if borrower else "the outstanding amount"
        await log_call_outcome({
            "borrower_id": borrower_id,
            "call_id": call_id,
            "intent": "PAY_LATER",
            "intent_history": state["intent_history"],
            "outcome": "COMMITTED",
            "commitment_date": extracted_date,
            "commitment_amount": amount,
        })
        return {
            "response": get_response(lang, "committed", amount=amount, date=extracted_date),
            "action": "end_call"
        }

    if intent == "CALLBACK_REQUESTED":
        state["awaiting"] = "callback_time"
        await save_conversation_state(call_id, state)
        await log_call_outcome({
            "borrower_id": borrower_id,
            "call_id": call_id,
            "intent": intent,
            "intent_history": state["intent_history"],
            "outcome": "CALLBACK_REQUESTED",
        })
        return {
            "response": get_response(lang, "callback"),
            "action": "continue"
        }

    if intent == "WRONG_NUMBER":
        await log_call_outcome({
            "borrower_id": borrower_id,
            "call_id": call_id,
            "intent": intent,
            "intent_history": state["intent_history"],
            "outcome": "WRONG_NUMBER",
        })
        await clear_conversation_state(call_id)
        return {
            "response": get_response(lang, "wrong_number"),
            "action": "end_call"
        }

    if intent == "DISPUTE":
        await log_call_outcome({
            "borrower_id": borrower_id,
            "call_id": call_id,
            "intent": intent,
            "intent_history": state["intent_history"],
            "outcome": "ESCALATED",
        })
        await clear_conversation_state(call_id)
        return {
            "response": get_response(lang, "dispute"),
            "action": "escalate"
        }

    # ── Fallback ───────────────────────────────────────────────────────────────
    await save_conversation_state(call_id, state)
    return {
        "response": get_response(lang, "fallback"),
        "action": "continue"
    }