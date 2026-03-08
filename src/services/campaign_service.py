from Config.db import borrowers_collection

async def get_due_borrowers() -> list:
    """Fetch all borrowers 1-30 days past due for outbound campaign."""
    cursor = borrowers_collection.find({
        "days_past_due": {"$gte": 1, "$lte": 30}
    })
    result = []
    async for b in cursor:
        b["_id"] = str(b["_id"])
        result.append(b)
    return result


async def get_borrowers_by_language(language: str) -> list:
    """Fetch due borrowers filtered by language — useful for batched dialing."""
    cursor = borrowers_collection.find({
        "days_past_due": {"$gte": 1, "$lte": 30},
        "language": language
    })
    result = []
    async for b in cursor:
        b["_id"] = str(b["_id"])
        result.append(b)
    return result