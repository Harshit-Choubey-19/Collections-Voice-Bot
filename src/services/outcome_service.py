from datetime import datetime
from Config.db import call_logs_collection, commitments_collection


def analyze_sentiment(intent_history: list, outcome: str) -> dict:
    """Derive sentiment from intent history and final outcome."""
    if not intent_history:
        return {"label": "NEUTRAL", "score": 0.5}

    negative_intents = {"ABUSIVE", "FINANCIAL_DIFFICULTY", "DISPUTE", "WRONG_NUMBER"}
    positive_intents = {"PAY_NOW", "CONFIRM_DATE"}

    negative_count = sum(1 for i in intent_history if i in negative_intents)
    positive_count = sum(1 for i in intent_history if i in positive_intents)
    total = len(intent_history)

    if outcome == "COMMITTED":
        return {"label": "POSITIVE", "score": round(0.7 + (positive_count / total) * 0.3, 2)}
    if outcome == "ESCALATED":
        return {"label": "NEGATIVE", "score": round(max(0.2 - (negative_count / total) * 0.2, 0.0), 2)}
    if outcome in ("WRONG_NUMBER", "NO_ANSWER"):
        return {"label": "NEUTRAL", "score": 0.5}
    if outcome == "CALLBACK_REQUESTED":
        return {"label": "NEUTRAL", "score": 0.55}

    if positive_count > negative_count:
        return {"label": "POSITIVE", "score": min(round(0.6 + (positive_count / total) * 0.3, 2), 1.0)}
    elif negative_count > positive_count:
        return {"label": "NEGATIVE", "score": max(round(0.4 - (negative_count / total) * 0.3, 2), 0.0)}
    return {"label": "NEUTRAL", "score": 0.5}


async def log_call_outcome(data: dict):
    """Log structured call outcome + sentiment to MongoDB."""
    intent_history = data.get("intent_history", [])
    outcome = data.get("outcome", "UNKNOWN")
    sentiment = analyze_sentiment(intent_history, outcome)

    record = {
        "borrower_id": data.get("borrower_id"),
        "call_id": data.get("call_id"),
        "intent": data.get("intent"),
        "intent_history": intent_history,
        "outcome": outcome,
        "commitment_date": data.get("commitment_date"),
        "commitment_amount": data.get("commitment_amount"),
        "callback_time": data.get("callback_time"),
        "escalated": outcome == "ESCALATED",
        "sentiment": sentiment,
        "duration_seconds": data.get("duration_seconds"),
        "timestamp": datetime.utcnow(),
    }

    await call_logs_collection.insert_one(record)
    print(f"[OUTCOME] Logged: {outcome} | Sentiment: {sentiment} | borrower: {data.get('borrower_id')}")

    if outcome == "COMMITTED" and data.get("commitment_date"):
        await commitments_collection.insert_one({
            "borrower_id": data.get("borrower_id"),
            "call_id": data.get("call_id"),
            "commitment_date": data.get("commitment_date"),
            "commitment_amount": data.get("commitment_amount"),
            "created_at": datetime.utcnow(),
        })
        print(f"[COMMITMENT] Saved for borrower: {data.get('borrower_id')}")


async def get_call_summary(borrower_id: str) -> dict:
    """Fetch all call logs + sentiment summary for a borrower."""
    cursor = call_logs_collection.find({"borrower_id": borrower_id})
    results = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)

    if not results:
        return {"logs": [], "summary": None}

    outcomes = [r.get("outcome") for r in results]
    sentiments = [r.get("sentiment", {}).get("label") for r in results]
    all_intents = []
    for r in results:
        all_intents.extend(r.get("intent_history", []))

    positive = sentiments.count("POSITIVE")
    negative = sentiments.count("NEGATIVE")
    neutral = sentiments.count("NEUTRAL")

    if positive >= negative and positive >= neutral:
        overall_sentiment = "POSITIVE"
    elif negative >= positive and negative >= neutral:
        overall_sentiment = "NEGATIVE"
    else:
        overall_sentiment = "NEUTRAL"

    return {
        "logs": results,
        "summary": {
            "total_calls": len(results),
            "outcomes": {
                "committed": outcomes.count("COMMITTED"),
                "escalated": outcomes.count("ESCALATED"),
                "no_answer": outcomes.count("NO_ANSWER"),
                "wrong_number": outcomes.count("WRONG_NUMBER"),
                "callback_requested": outcomes.count("CALLBACK_REQUESTED"),
            },
            "overall_sentiment": overall_sentiment,
            "sentiment_breakdown": {
                "positive": positive,
                "negative": negative,
                "neutral": neutral
            },
            "most_common_intent": max(set(all_intents), key=all_intents.count) if all_intents else None,
            "last_call_at": str(results[-1].get("timestamp")) if results else None,
        }
    }