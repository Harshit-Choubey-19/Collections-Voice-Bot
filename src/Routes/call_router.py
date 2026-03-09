from fastapi import APIRouter, HTTPException, Request
from bson import ObjectId

from Config.db import borrowers_collection
from Models.inya import InyaResponse, InyaStartCall
from services.conversation_service import (
    build_opening_message,
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
# DYNAMIC GREETING
# GET /api/call/greeting?borrower_id=xxx&call_id=xxx
# Returns Inya Dynamic Message format
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/call/greeting")
async def get_greeting(
    borrower_id: str,
    call_id: str = None,
    sender_id: str = None,        # ← Inya sends this
    flow_id: str = None,
    language: str = "en",
    is_initial: str = None,
    phone_number: str = None,
    organization_id: str = None,
    environment: str = None,
    user_id: str = None,
    mobile: str = None,
):
    # Use call_id OR sender_id — whichever Inya sends
    effective_call_id = call_id or sender_id or borrower_id

    print(f"[GREETING] borrower_id={borrower_id} call_id={call_id} sender_id={sender_id} effective={effective_call_id}")

    try:
        greeting_text = await build_opening_message(
            borrower_id=borrower_id,
            call_id=effective_call_id,
            language=language
        )

        borrower = await borrowers_collection.find_one({"_id": ObjectId(borrower_id)})

        return {
            "additional_info": {
                "inya_data": {
                    "text": greeting_text,
                    "user_context": {
                        "phone_number": borrower.get("phone", "") if borrower else "",
                        "name": borrower.get("name", "") if borrower else "",
                        "emi_amount": str(borrower.get("emi_amount", "")) if borrower else "",
                        "due_date": str(borrower.get("due_date", "")) if borrower else "",
                        "days_past_due": str(borrower.get("days_past_due", "")) if borrower else "",
                        "borrower_id": borrower_id,
                        "call_id": effective_call_id   # ← send back to Inya
                    }
                }
            }
        }

    except Exception as e:
        print(f"[GREETING ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# CALL START (optional fallback)
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/call/start")
async def start_call(data: InyaStartCall):
    try:
        message = await build_opening_message(
            borrower_id=data.borrower_id,
            call_id=data.call_id,
            language=data.language or "en"
        )
        return {"message": message}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# PROCESS MESSAGE — On-Call action
# POST /api/call/message
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

        # Return full dict — let Inya extract "response" field via After API Call Variables
        return {
            "response": result["response"],
            "action": result["action"]
        }

    except Exception as e:
        print(f"[MESSAGE ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# CALL END — Post-Call action
# POST /api/call/end
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

        if event in ("no_answer", "call_failed", "voicemail", "busy"):
            outcome = "NO_ANSWER"
            retry_count = await increment_retry(borrower_id) if borrower_id else 0
            exceeded = await exceeded_retries(borrower_id) if borrower_id else False
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
# CAMPAIGN
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/call/campaign/due-borrowers")
async def get_campaign_borrowers():
    try:
        borrowers = await get_due_borrowers()
        return {"message": "Due borrowers fetched", "count": len(borrowers), "data": borrowers}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# CALL HISTORY + SENTIMENT
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