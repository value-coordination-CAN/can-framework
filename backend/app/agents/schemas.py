from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AgentRegister(BaseModel):
    did: str = Field(..., max_length=400, description="did:key of the agent (Ed25519)")
    name: str = Field(..., min_length=1, max_length=200)
    model: str | None = Field(default=None, max_length=200, description="model or software version")
    contact: str = Field(..., min_length=3, max_length=300,
                         description="Published in the open register: how anyone affected reaches you")
    steward_name_public: bool = Field(default=False, description="Publish your display name beside the contact")
    scopes: list[str] = Field(default_factory=list)
    max_unreviewed: int | None = Field(default=None, ge=1, le=10000)


class AgentUpdate(BaseModel):
    scopes: list[str] | None = None
    max_unreviewed: int | None = Field(default=None, ge=1, le=10000)
    contact: str | None = Field(default=None, min_length=3, max_length=300)
    steward_name_public: bool | None = None
    status: str | None = Field(default=None, pattern="^(active|suspended|revoked)$")
    reason: str | None = Field(default=None, max_length=500)


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    did: str
    name: str
    model: str | None
    steward_user_id: str
    contact: str | None
    scopes: list
    status: str
    max_unreviewed: int | None
    revoked_reason: str | None
    steward_name_public: bool


class PublicAgentOut(BaseModel):
    """What the open register shows: enough to find whoever answers for an agent,
    and nothing about what the agent wrote or about whom."""
    id: str
    did: str
    name: str
    model: str | None
    status: str
    scopes: list
    created_at: datetime
    revoked_at: datetime | None = None
    revoked_reason: str | None = None
    contact: str | None
    steward_name: str | None = None
    records: dict
    participation: dict



class AgentVerifyIn(BaseModel):
    did: str = Field(..., max_length=400)
    challenge: str = Field(..., max_length=200)
    signature_b64url: str = Field(..., max_length=200)


class AgentVerifyOut(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    agent_id: str
    steward_user_id: str
    scopes: list
    queue: dict


class DerivedRecordIn(BaseModel):
    kind: str = Field(..., max_length=40)
    subject_ref: str = Field(..., min_length=1, max_length=200, description='What it is about, e.g. "asset:<id>"')
    statement: str = Field(..., min_length=1, max_length=5000, description="What it says, readable by a person")
    inputs: dict = Field(..., description="The records it used, by reference and value")
    output: dict = Field(..., description="The result, in a form that can be compared exactly")
    method: str = Field(..., min_length=1, max_length=300, description="Model or code version: enough to reproduce")
    confidence: float | None = Field(default=None, ge=0, le=1)


class DerivedRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    agent_id: str
    kind: str
    subject_ref: str
    statement: str
    inputs: dict
    inputs_hash: str
    output: dict
    output_hash: str
    method: str
    confidence: float | None
    status: str
    recompute_status: str
    review_note: str | None
    reviewed_at: datetime | None


class ReviewIn(BaseModel):
    accept: bool
    note: str = Field(..., min_length=1, max_length=5000)


class RecomputeIn(BaseModel):
    output: dict
    method: str = Field(..., min_length=1, max_length=300)
    note: str | None = Field(default=None, max_length=5000)


class RecomputationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    record_id: str
    by_subject: str
    output_hash: str
    method: str
    result: str
    note: str | None
