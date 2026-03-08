from pydantic import BaseModel
from typing import Optional


class InyaMessage(BaseModel):
    call_id: str
    borrower_id: str
    text: str
    language: Optional[str] = "en"
    turn_index: Optional[int] = None
    phone_number: Optional[str] = None
    flow_id: Optional[str] = None
    organization_id: Optional[str] = None
    environment: Optional[str] = None
    user_id: Optional[str] = None
    sender_id: Optional[str] = None
    mobile: Optional[str] = None

    class Config:
        extra = "allow"


class InyaCallEvent(BaseModel):
    call_id: Optional[str] = None
    borrower_id: Optional[str] = None
    event: Optional[str] = "call_ended"
    duration_seconds: Optional[int] = None
    reason: Optional[str] = None
    phone_number: Optional[str] = None
    flow_id: Optional[str] = None
    organization_id: Optional[str] = None
    environment: Optional[str] = None
    user_id: Optional[str] = None
    sender_id: Optional[str] = None
    mobile: Optional[str] = None

    class Config:
        extra = "allow"


class InyaStartCall(BaseModel):
    call_id: str
    borrower_id: str
    language: Optional[str] = "en"


class InyaResponse(BaseModel):
    response: str
    action: str = "continue"
    context: Optional[dict] = None