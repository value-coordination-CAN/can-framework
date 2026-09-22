from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LedgerEntryCreate(BaseModel):
    # Omit (or use your own id) to record about yourself; recording about someone else needs can_attester.
    user_id: str | None = None
    ledger_type: str = Field(..., pattern="^(contribution|reliability|care)$")
    metric: str = Field(..., min_length=1, max_length=100)
    value: float = Field(..., ge=0.0, le=1.0, description="Normalised 0..1")
    evidence_ref: str | None = Field(default=None, max_length=500)


class LedgerEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    ledger_type: str
    metric: str
    value: float
    evidence_ref: str | None
    self_reported: bool
    status: str  # active|superseded
    superseded_reason: str | None = None
    supersedes_id: str | None = None


class DisputeCreate(BaseModel):
    reason: str = Field(..., min_length=1, max_length=5000)
    proposed_value: float | None = Field(default=None, ge=0.0, le=1.0)


class DisputeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    entry_id: str
    user_id: str
    reason: str
    proposed_value: float | None
    status: str
    resolved_at: datetime | None = None
    resolution_note: str | None = None
    corrected_entry_id: str | None = None


class DisputeResolveIn(BaseModel):
    outcome: str = Field(..., pattern="^(corrected|removed|rejected)$")
    note: str = Field(..., min_length=1, max_length=5000)
    corrected_value: float | None = Field(default=None, ge=0.0, le=1.0)
