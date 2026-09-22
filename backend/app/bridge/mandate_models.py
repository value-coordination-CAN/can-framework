import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class PaymentMandate(Base):
    """What an agent may spend, on whose authority, on what, and until when (WP-013 §3).

    A payment mandate is granted by the person whose money it is, to a named agent, and it
    is revocable at any moment. Everything an agent pays must fall inside one.
    """
    __tablename__ = "bw_payment_mandates"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("ag_agents.id"), index=True)
    granted_by_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    purposes: Mapped[list] = mapped_column(JSON)              # what it may pay for, by name
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    max_per_payment: Mapped[float] = mapped_column(Float)
    max_total: Mapped[float] = mapped_column(Float)
    spent_total: Mapped[float] = mapped_column(Float, default=0.0)
    payee_user_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)  # None: anyone
    requires_evidence: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|revoked|exhausted
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class AgentPayment(Base):
    """Every attempt an agent makes, settled or refused.

    Refusals are kept deliberately: an audit trail that records only what succeeded tells
    the person nothing about what their agent tried to do.
    """
    __tablename__ = "bw_agent_payments"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    mandate_id: Mapped[str | None] = mapped_column(String, ForeignKey("bw_payment_mandates.id"), nullable=True)
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("ag_agents.id"), index=True)
    payer_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    payee_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(10))
    purpose: Mapped[str] = mapped_column(String(200))
    evidence_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20))            # settled|refused
    refusal_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rail: Mapped[str | None] = mapped_column(String(50), nullable=True)
    settlement_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # The trusted transaction object: what travelled with the money (WP-013)
    transaction_object: Mapped[dict | None] = mapped_column(JSON, nullable=True)
