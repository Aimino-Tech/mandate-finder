import uuid
from datetime import datetime

from pydantic import BaseModel


class ProfileMatchResponse(BaseModel):
    id: uuid.UUID
    profile_id: uuid.UUID
    job_posting_id: uuid.UUID
    score: float
    reasoning: str | None
    created_at: datetime
    user_feedback: str | None
    notified_at: datetime | None
    is_new: bool

    model_config = {"from_attributes": True}


class FeedbackUpdate(BaseModel):
    feedback: str
