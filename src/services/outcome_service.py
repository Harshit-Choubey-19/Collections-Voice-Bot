from datetime import datetime
from Config.db import call_logs_collection

async def log_call_outcome(data):

    await call_logs_collection.insert_one({

        "borrower_id": data.borrower_id,
        "intent": data.intent,
        "commitment_date": data.commitment_date,
        "commitment_amount": data.commitment_amount,
        "timestamp": datetime.utcnow()
    })