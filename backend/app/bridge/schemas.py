from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    currency: str = Field(default="USD", pattern="^[A-Z]{3}$")
    target_amount: float = Field(..., gt=0)
    unit_value: float = Field(default=1000.0, gt=0)
    asset_id: str | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    sponsor_user_id: str
    name: str
    description: str | None
    currency: str
    target_amount: float
    unit_value: float
    status: str
    asset_id: str | None


class ProjectStatusIn(BaseModel):
    status: str = Field(..., pattern="^(funding|funded|delivering|operating|closed)$")


class ContributionCreate(BaseModel):
    source_type: str = Field(..., pattern="^(capital|participation_units|in_kind|pre_committed_use|community)$")
    description: str = Field(..., min_length=1, max_length=5000)
    offered_value: float = Field(..., gt=0)
    wants: str = Field(default="participation", pattern="^(participation|access|both)$")
    access_terms: dict | None = None


class ContributionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    project_id: str
    contributor_user_id: str
    source_type: str
    description: str
    offered_value: float
    accepted_value: float | None
    valuation_basis: str | None
    wants: str
    access_terms: dict | None
    status: str
    decision_note: str | None


class ContributionDecisionIn(BaseModel):
    accept: bool
    accepted_value: float | None = Field(default=None, gt=0)
    valuation_basis: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=5000)


class AgreementCreate(BaseModel):
    supplier_user_id: str
    scope: str = Field(..., min_length=1, max_length=5000)
    cash_share: float = Field(1.0, ge=0, le=1)


class AgreementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    supplier_user_id: str
    scope: str
    cash_share: float
    participation_share: float
    accepted_by_supplier: str
    status: str


class AgreementResponseIn(BaseModel):
    accept: bool


class InvoiceCreate(BaseModel):
    amount: float = Field(..., gt=0)
    description: str = Field(..., min_length=1, max_length=5000)
    delivery_evidence_ref: str | None = Field(default=None, max_length=500)


class InvoiceVerifyIn(BaseModel):
    approve: bool = True
    delivery_evidence_ref: str | None = Field(default=None, max_length=500)


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    agreement_id: str
    amount: float
    description: str
    delivery_evidence_ref: str | None
    status: str
    paid_at: datetime | None
    settlement_ref: str | None


class PledgeCreate(BaseModel):
    amount: float = Field(..., gt=0)
    lender_user_id: str | None = None
    note: str | None = Field(default=None, max_length=500)


class PledgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    holding_id: str
    lender_user_id: str | None
    amount: float
    note: str | None
    status: str


class SettleIn(BaseModel):
    amount: float = Field(..., gt=0, description="Units of the holding to settle into money")
    rail: str | None = Field(default=None, description="Settlement rail; defaults to the simulated rail")


class TransferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    direction: str
    from_layer: str
    to_layer: str
    amount: float
    currency: str | None
    rail: str
    external_ref: str | None
    status: str
