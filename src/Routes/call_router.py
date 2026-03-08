from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from bson import ObjectId

from Config.db import borrowers_collection
from Models.inya import InyaResponse, InyaStartCall
from services.conversation_service import (
    process_conversation,
    clear_conversation_state,
    save_conversation_state,
    get_conversation_state,
)
from services.outcome_service import log_call_outcome, get_call_summary
from services.campaign_service import get_due_borrowers
from utils.retry_manager import increment_retry, exceeded_retries

router = APIRouter()


# ──────────────────────────────────────────────────────────────────────────────
# DYNAMIC GREETING — Inya Dynamic Message webhook
# GET /api/call/greeting?borrower_id=xxx&call_id=xxx
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/call/greeting")
async def get_greeting(
    borrower_id: str,
    call_id: str = None,
    language: str = "en",
    is_initial: str = None
):
    print(f"[GREETING] borrower_id received: {borrower_id}")
    try:
        borrower = await borrowers_collection.find_one({"_id": ObjectId(borrower_id)})
        print(f"[GREETING] borrower found: {borrower}")

        if not borrower:
            return {
                "additional_info": {
                    "inya_data": {
                        "text": "Hello, this is a call regarding your loan account. Please contact us.",
                        "user_context": {}
                    }
                }
            }

        # Initialize Redis state using Inya's call_id
        if call_id:
            await save_conversation_state(call_id, {
                "turn": 0,
                "intent_history": [],
                "awaiting": None,
                "language": language,
                "borrower_id": borrower_id
            })

        greeting_text = (
            f"Hello, am I speaking with {borrower['name']}? "
            f"This is a call from your lending institution regarding "
            f"your EMI of ₹{borrower['emi_amount']} which was due on "
            f"{borrower['due_date']} and is currently {borrower['days_past_due']} "
            f"days overdue. When will you be able to make this payment?"
        )

        return {
            "additional_info": {
                "inya_data": {
                    "text": greeting_text,
                    "user_context": {
                        "phone_number": borrower.get("phone", ""),
                        "name": borrower.get("name", ""),
                        "emi_amount": str(borrower.get("emi_amount", "")),
                        "due_date": str(borrower.get("due_date", "")),
                        "days_past_due": str(borrower.get("days_past_due", "")),
                        "borrower_id": borrower_id,
                        "call_id": call_id or ""
                    }
                }
            }
        }

    except Exception as e:
        print(f"[GREETING ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# CALL START — when call connects (optional, Inya may not use this)
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/call/start")
async def start_call(data: InyaStartCall):
    try:
        borrower = await borrowers_collection.find_one({"_id": ObjectId(data.borrower_id)})
        if not borrower:
            return {"message": "Hello, this is a call regarding your loan account."}

        await save_conversation_state(data.call_id, {
            "turn": 0,
            "intent_history": [],
            "awaiting": None,
            "language": data.language,
            "borrower_id": data.borrower_id
        })

        return {
            "message": (
                f"Hello, am I speaking with {borrower['name']}? "
                f"This is a call regarding your EMI of ₹{borrower['emi_amount']} "
                f"due on {borrower['due_date']}. When can you make the payment?"
            )
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# PROCESS MESSAGE — On-Call action (every borrower utterance)
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/call/message")
async def handle_message(request: Request):
    try:
        body = await request.json()
        print(f"[MESSAGE] Received: {body}")

        call_id = body.get("call_id") or body.get("sender_id")
        borrower_id = body.get("borrower_id")
        text = body.get("text") or body.get("user_input") or body.get("asr_text", "")

        if not borrower_id or not text:
            return {"response": "I'm sorry, could you please repeat that?", "action": "continue"}

        result = await process_conversation(
            borrower_id=borrower_id,
            text=text,
            call_id=call_id
        )

        print(f"[MESSAGE] Response: {result}")

        # Return plain text — Inya speaks this directly
        return result["response"]

    except Exception as e:
        print(f"[MESSAGE ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# CALL END — Post-Call action (logs outcome + sentiment)
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/call/end")
async def end_call(request: Request):
    try:
        body = await request.json()
        print(f"[CALL END] Received: {body}")

        call_id = body.get("call_id") or body.get("sender_id")
        borrower_id = body.get("borrower_id")
        event = body.get("event", "call_ended")
        duration = body.get("duration_seconds")

        # Get Redis state BEFORE clearing
        state = {}
        if call_id:
            state = await get_conversation_state(call_id)
            await clear_conversation_state(call_id)

        intent_history = state.get("intent_history", [])

        # Determine outcome
        if event in ("no_answer", "call_failed", "voicemail", "busy"):
            outcome = "NO_ANSWER"
            if borrower_id:
                retry_count = await increment_retry(borrower_id)
                exceeded = await exceeded_retries(borrower_id)
            else:
                retry_count, exceeded = 0, False
        else:
            last_intent = intent_history[-1] if intent_history else "UNKNOWN"
            outcome_map = {
                "PAY_NOW": "COMMITTED",
                "CONFIRM_DATE": "COMMITTED",
                "PAY_LATER": "PAY_LATER",
                "FINANCIAL_DIFFICULTY": "ESCALATED",
                "ABUSIVE": "ESCALATED",
                "DISPUTE": "ESCALATED",
                "WRONG_NUMBER": "WRONG_NUMBER",
                "CALLBACK_REQUESTED": "CALLBACK_REQUESTED",
                "UNKNOWN": "UNKNOWN",
            }
            outcome = outcome_map.get(last_intent, "UNKNOWN")
            retry_count, exceeded = 0, False

        # Log to MongoDB
        if borrower_id:
            await log_call_outcome({
                "borrower_id": borrower_id,
                "call_id": call_id,
                "intent": intent_history[-1] if intent_history else "UNKNOWN",
                "intent_history": intent_history,
                "outcome": outcome,
                "commitment_date": state.get("commitment_date"),
                "commitment_amount": None,
                "duration_seconds": duration,
            })

            # Sentiment summary after logging
            summary = await get_call_summary(borrower_id)
            print(f"[SENTIMENT] {summary.get('summary')}")

            return {
                "message": "Call ended and outcome logged",
                "outcome": outcome,
                "sentiment": summary.get("summary", {}).get("overall_sentiment"),
                "retry_count": retry_count,
                "schedule_retry": not exceeded if outcome == "NO_ANSWER" else False
            }

        return {"message": "Call ended", "event": event}

    except Exception as e:
        print(f"[CALL END ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# CAMPAIGN — due borrowers for outbound dialing
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/call/campaign/due-borrowers")
async def get_campaign_borrowers():
    try:
        borrowers = await get_due_borrowers()
        return {"message": "Due borrowers fetched", "count": len(borrowers), "data": borrowers}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# CALL HISTORY + SENTIMENT SUMMARY
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/call/history/{borrower_id}")
async def call_history(borrower_id: str):
    try:
        result = await get_call_summary(borrower_id)
        return {
            "message": "Call history fetched",
            "data": result["logs"],
            "summary": result["summary"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))