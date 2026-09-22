from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AssetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    kind: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=5000)
    currency: str = Field(default="USD", pattern="^[A-Z]{3}$")


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    kind: str
    description: str | None
    currency: str
    holder_user_id: str
    created_at: datetime


class EvidenceCreate(BaseModel):
    category: str = Field(..., min_length=1, max_length=50)
    key: str = Field(..., min_length=1, max_length=100)
    value: float | None = None
    text: str | None = Field(default=None, max_length=5000)
    unit: str | None = Field(default=None, max_length=50)
    evidence_ref: str | None = Field(default=None, max_length=500)


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    recorded_at: datetime
    category: str
    key: str
    value: float | None
    text: str | None
    unit: str | None
    evidence_ref: str | None
    self_reported: bool
    superseded_at: datetime | None


class MandateIn(BaseModel):
    enabled: bool
    alert_drop_pct: float = Field(10, ge=0, le=100)
    min_confidence: float = Field(0.6, ge=0, le=1)
    flag_liability: bool = True
    allowed_actions: list[str] = Field(default_factory=lambda: ["alert", "request_attestation", "request_review"])


class ShareIn(BaseModel):
    grantee_user_id: str
    categories: list[str] = Field(..., min_length=1)


class ShareOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    grantee_user_id: str
    categories: list[str]


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    triggered_by: str
    base_value: float | None
    confidence: float
    steps: dict
    actions: list
