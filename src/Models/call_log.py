from pydantic import BaseModel
from typing import Optional

class CallLog(BaseModel):

    borrower_id: str
    intent: str
    commitment_date: Optional[str]
    commitment_amount: Optional[int]