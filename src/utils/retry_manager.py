from Config.redis import redis_client
from dotenv import load_dotenv
import os

load_dotenv()

MAX_CALL_RETRIES = int(os.getenv("MAX_CALL_RETRIES"))

def increment_retry(borrower_id):

    key = f"retry:{borrower_id}"

    count = redis_client.get(key)

    if count is None:
        redis_client.set(key, 1)
        return 1

    count = int(count) + 1
    redis_client.set(key, count)

    return count


def exceeded_retries(borrower_id):

    key = f"retry:{borrower_id}"

    count = redis_client.get(key)

    if count and int(count) >= MAX_CALL_RETRIES:
        return True

    return False