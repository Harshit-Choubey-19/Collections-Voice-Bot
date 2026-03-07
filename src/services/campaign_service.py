from Config.db import borrowers_collection

async def get_due_borrowers():

    borrowers = borrowers_collection.find({
        "days_past_due": {"$gte": 1, "$lte": 30}
    })

    result = []

    async for b in borrowers:
        result.append(b)

    return result