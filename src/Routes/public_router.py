from fastapi import APIRouter

router = APIRouter(prefix="/api/v1")

@router.get("/")
async def root():
    return {"message": "Collections Voice Bot Running"}    