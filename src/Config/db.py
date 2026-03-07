import motor.motor_asyncio
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL")
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
db = client["collection_voice_bot"]

borrowers_collection = db.borrowers
call_logs_collection = db.call_logs
commitments_collection = db.commitments



