from pydantic import BaseModel

class Borrower(BaseModel):

    borrower_id: str
    name: str
    phone: str
    emi_amount: int
    due_date: str
    days_past_due: int
    language: str