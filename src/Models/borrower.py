from pydantic import BaseModel, Field

class Borrower(BaseModel):
    name: str = Field(..., message="Name is required")
    phone: str = Field(..., message="Phone is required")
    emi_amount: int = Field(..., message="EMI amount is required")
    due_date: str
    days_past_due: int
    language: str