import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Asset(Base):
    """An asset whose value is carried as evidence rather than a bare price."""
    __tablename__ = "va_assets"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    holder_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    # The holder's explicit, revocable delegation to the assurance agent.
    mandate: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AssetEvidence(Base):
    __tablename__ = "va_evidence"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    asset_id: Mapped[str] = mapped_column(String, ForeignKey("va_assets.id"), index=True)
    category: Mapped[str] = mapped_column(String(50))
    key: Mapped[str] = mapped_column(String(100))
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    evidence_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attester_subject: Mapped[str | None] = mapped_column(String(400), nullable=True)
    self_reported: Mapped[bool] = mapped_column(Boolean, default=True)
    # Newer evidence for the same key supersedes older evidence; history is kept.
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AssetShare(Base):
    """Selective disclosure: the holder shares chosen categories with a named person."""
    __tablename__ = "va_shares"
    __table_args__ = (UniqueConstraint("asset_id", "grantee_user_id", name="uq_va_shares_asset_grantee"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    asset_id: Mapped[str] = mapped_column(String, ForeignKey("va_assets.id"), index=True)
    grantee_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    categories: Mapped[list] = mapped_column(JSON)  # evidence categories, plus "valuation"


class EvidenceProposal(Base):
    """A revaluation someone proposes: an agent or a person suggesting an input has moved.

    A proposal is not evidence. It becomes evidence only when the holder or an attester
    accepts it, which is what keeps agents from attesting to things they cannot witness.
    """
    __tablename__ = "va_evidence_proposals"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    asset_id: Mapped[str] = mapped_column(String, ForeignKey("va_assets.id"), index=True)
    proposed_by: Mapped[str] = mapped_column(String(400))            # DID or OIDC subject
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(50))
    key: Mapped[str] = mapped_column(String(100))
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_ref: Mapped[str] = mapped_column(String(500))             # where the figure came from
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|accepted|rejected
    decided_by: Mapped[str | None] = mapped_column(String(400), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_id: Mapped[str | None] = mapped_column(String, ForeignKey("va_evidence.id"), nullable=True)


class AssuranceRun(Base):
    """One pass of the agentic loop: detect, interpret, recalculate, explain, act."""
    __tablename__ = "va_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    asset_id: Mapped[str] = mapped_column(String, ForeignKey("va_assets.id"), index=True)
    triggered_by: Mapped[str] = mapped_column(String(400))
    inputs: Mapped[dict] = mapped_column(JSON)
    base_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    steps: Mapped[dict] = mapped_column(JSON)
    actions: Mapped[list] = mapped_column(JSON)
