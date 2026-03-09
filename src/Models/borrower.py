from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class Language(str, Enum):
    english = "en"
    hindi = "hi"
    kannada = "kn"
    tamil = "ta"
    telugu = "te"
    marathi = "mr"


class Borrower(BaseModel):
    name: str = Field(..., description="Full name of borrower")
    phone: str = Field(..., description="Mobile number with country code")
    emi_amount: float = Field(..., description="EMI amount in INR", gt=0)
    due_date: str = Field(..., description="EMI due date e.g. 2025-06-01")
    days_past_due: int = Field(..., description="Days past due (1-30)", ge=1, le=30)
    language: Optional[str] = Field(default="en", description="Preferred language code")
    loan_account_number: Optional[str] = None