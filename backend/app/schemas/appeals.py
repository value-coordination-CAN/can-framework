from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AppealCreate(BaseModel):
    request_id: str
    reason: str = Field(..., min_length=1, max_length=5000)


class AppealOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    request_id: str
    reason: str
    status: str
    resolved_at: datetime | None = None
    resolution_note: str | None = None


class AppealResolveIn(BaseModel):
    outcome: str = Field(..., pattern="^(upheld|rejected)$")
    note: str = Field(..., min_length=1, max_length=5000)
