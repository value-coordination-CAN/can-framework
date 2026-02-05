from pydantic import BaseModel, Field

class LedgerEntryCreate(BaseModel):
    user_id: str
    ledger_type: str = Field(..., pattern="^(contribution|reliability|care)$")
    metric: str = Field(..., min_length=1, max_length=100)
    value: float = Field(..., ge=0.0)
    evidence_ref: str | None = Field(default=None, max_length=500)

class LedgerEntryOut(BaseModel):
    id: str
    user_id: str
    ledger_type: str
    metric: str
    value: float
    evidence_ref: str | None

    class Config:
        from_attributes = True
