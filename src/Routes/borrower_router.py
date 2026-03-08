from fastapi import APIRouter, HTTPException
from Config.db import borrowers_collection
from Models.borrower import Borrower
from bson import ObjectId
import uuid

router = APIRouter()

#set borrower details
@router.post("/borrower", status_code=201)
async def add_borrower(data: Borrower):
    try:
        payload = data.model_dump()

        # Auto-assign borrower_id if not provided
        if not payload.get("borrower_id"):
            payload["borrower_id"] = str(uuid.uuid4())

        result = await borrowers_collection.insert_one(payload)
        payload["_id"] = str(result.inserted_id)

        return {"message": "Borrower added successfully", "data": payload}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add borrower: {str(e)}")
    
@router.get("/borrower/search")
async def search_borrower(borrower_id: str):
    try:
        borrower = await borrowers_collection.find_one({"_id": ObjectId(borrower_id)})
        if not borrower:
            raise HTTPException(status_code=404, detail="Borrower not found")
        borrower["_id"] = str(borrower["_id"])
        return {"message": "Borrower fetched successfully", "data": borrower}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

#get borrower by borrower_id or _id
@router.get("/borrower/{borrower_id}")
async def get_borrower(borrower_id: str):
    try:
        # Try borrower_id field first, then _id
        borrower = await borrowers_collection.find_one({"borrower_id": borrower_id})
        if not borrower:
            borrower = await borrowers_collection.find_one({"_id": ObjectId(borrower_id)})

        if not borrower:
            raise HTTPException(status_code=404, detail="Borrower not found")

        borrower["_id"] = str(borrower["_id"])
        return {"message": "Borrower fetched successfully", "data": borrower}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/borrowers")
async def list_borrowers():
    """List all borrowers (for CRM dashboard use)."""
    try:
        cursor = borrowers_collection.find({})
        results = []
        async for b in cursor:
            b["_id"] = str(b["_id"])
            results.append(b)
        return {"message": "Borrowers fetched successfully", "data": results, "count": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))