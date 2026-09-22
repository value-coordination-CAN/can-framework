from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AllocationRequestCreate(BaseModel):
    pool: str = Field(..., pattern="^(housing|transport|food|energy|learning)$")
    description: str = Field(..., min_length=1, max_length=5000)


class AllocationRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    pool: str
    description: str
    status: str
    priority_score: float | None
    score_snapshot_id: str | None = None
    decided_at: datetime | None = None
    decision_reason: str | None = None


class AllocationRequestDetail(AllocationRequestOut):
    score_explanation: dict | None = None


class AllocationDecisionIn(BaseModel):
    decision: str = Field(..., pattern="^(approved|declined)$")
    reason: str = Field(..., min_length=1, max_length=5000)
