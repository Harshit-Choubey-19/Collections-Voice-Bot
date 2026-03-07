from pydantic import BaseModel

class Commitment(BaseModel):

    borrower_id: str
    commitment_date: str
    commitment_amount: int