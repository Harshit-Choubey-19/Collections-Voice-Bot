from Config.redis import redis_client
from dotenv import load_dotenv
import os

load_dotenv()

MAX_CALL_RETRIES = int(os.getenv("MAX_CALL_RETRIES", 3))


async def increment_retry(borrower_id: str) -> int:
    """Increment retry count for a borrower. Returns new count."""
    key = f"retry:{borrower_id}"
    count = await redis_client.get(key)

    if count is None:
        await redis_client.set(key, 1, ex=86400)  # expires in 24 hours
        return 1

    new_count = int(count) + 1
    await redis_client.set(key, new_count, ex=86400)
    return new_count


async def exceeded_retries(borrower_id: str) -> bool:
    """Check if borrower has exceeded max retry attempts."""
    key = f"retry:{borrower_id}"
    count = await redis_client.get(key)
    return bool(count and int(count) >= MAX_CALL_RETRIES)


async def reset_retries(borrower_id: str):
    """Reset retry counter after successful commitment."""
    await redis_client.delete(f"retry:{borrower_id}")