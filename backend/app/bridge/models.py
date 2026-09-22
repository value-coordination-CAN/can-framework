import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base

# The three layers of the bridge wallet (WP-010 §1)
LAYER_FIAT = "fiat"
LAYER_MODERNISED = "modernised_fiat"
LAYER_DIRECT = "direct_value"
LAYERS = (LAYER_FIAT, LAYER_MODERNISED, LAYER_DIRECT)

# What a holding can be. Each kind belongs to one layer.
HOLDING_KINDS = {
    "cash": LAYER_FIAT,
    "tokenised_deposit": LAYER_MODERNISED,
    "offline_value": LAYER_MODERNISED,
    "participation_unit": LAYER_DIRECT,
    "access_right": LAYER_DIRECT,
    "claim": LAYER_DIRECT,            # e.g. a verified invoice or dividend
    "entitlement": LAYER_DIRECT,      # e.g. a floor entitlement (WP-009)
    "credit": LAYER_DIRECT,           # e.g. a carbon credit
}

# Direct value that can settle down into money. An access right or a floor entitlement is a
# right to use something, not a claim for cash, so it is held or transferred, never settled.
SETTLEABLE_KINDS = ("participation_unit", "claim", "credit")

# How a project is funded (WP-010 §3)
SOURCE_TYPES = ("capital", "participation_units", "in_kind", "pre_committed_use", "community")
CASH_SOURCES = ("capital",)


def _uuid() -> str:
    return str(uuid.uuid4())


class Wallet(Base):
    __tablename__ = "bw_wallets"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), unique=True, index=True)


class Holding(Base):
    """One position in one layer. Direct-value holdings carry their own evidence and terms."""
    __tablename__ = "bw_holdings"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    wallet_id: Mapped[str] = mapped_column(String, ForeignKey("bw_wallets.id"), index=True)
    layer: Mapped[str] = mapped_column(String(30))
    kind: Mapped[str] = mapped_column(String(40))
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String, ForeignKey("bw_projects.id"), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    terms: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evidence_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Project(Base):
    __tablename__ = "bw_projects"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sponsor_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    target_amount: Mapped[float] = mapped_column(Float)
    unit_value: Mapped[float] = mapped_column(Float, default=1000.0)  # value of one participation unit
    status: Mapped[str] = mapped_column(String(30), default="funding")  # funding|funded|delivering|operating|closed
    # Optional link to the asset whose value this project creates (WP-011)
    asset_id: Mapped[str | None] = mapped_column(String, ForeignKey("va_assets.id"), nullable=True)


class Contribution(Base):
    """Capital, participation, in-kind value, pre-committed use or community contribution."""
    __tablename__ = "bw_contributions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    project_id: Mapped[str] = mapped_column(String, ForeignKey("bw_projects.id"), index=True)
    contributor_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text)
    offered_value: Mapped[float] = mapped_column(Float)          # what the contributor says it is worth
    accepted_value: Mapped[float | None] = mapped_column(Float, nullable=True)  # what the sponsor valued it at
    valuation_basis: Mapped[str | None] = mapped_column(String(500), nullable=True)
    wants: Mapped[str] = mapped_column(String(30), default="participation")  # participation|access|both
    access_terms: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="proposed")  # proposed|accepted|rejected|withdrawn
    decided_by: Mapped[str | None] = mapped_column(String(400), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class SupplierAgreement(Base):
    """A supplier's split between cash now and a verified stake in what they help build (WP-010 §4)."""
    __tablename__ = "bw_supplier_agreements"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    project_id: Mapped[str] = mapped_column(String, ForeignKey("bw_projects.id"), index=True)
    supplier_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    scope: Mapped[str] = mapped_column(Text)
    cash_share: Mapped[float] = mapped_column(Float, default=1.0)           # 0..1 of each invoice paid in money
    participation_share: Mapped[float] = mapped_column(Float, default=0.0)  # the rest, as participation units
    accepted_by_supplier: Mapped[str] = mapped_column(String(10), default="pending")  # pending|accepted|declined
    status: Mapped[str] = mapped_column(String(30), default="active")


class SupplierInvoice(Base):
    """Payment with proof: an invoice on the same record as the certified delivery."""
    __tablename__ = "bw_supplier_invoices"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    agreement_id: Mapped[str] = mapped_column(String, ForeignKey("bw_supplier_agreements.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    description: Mapped[str] = mapped_column(Text)
    delivery_evidence_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="submitted")  # submitted|verified|paid|rejected
    verified_by: Mapped[str | None] = mapped_column(String(400), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    settlement_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)


class Pledge(Base):
    """Value → money leverage: a verified holding pledged for liquidity without being sold.
    Double pledging is impossible to hide: the pledged amount is checked against the holding."""
    __tablename__ = "bw_pledges"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    holding_id: Mapped[str] = mapped_column(String, ForeignKey("bw_holdings.id"), index=True)
    lender_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    amount: Mapped[float] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active")  # active|released
    released_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class BridgeTransfer(Base):
    """A movement between layers: settle down to money, convert across, or prove and pledge up.

    PLACEHOLDER: settlement is recorded and simulated. A real deployment plugs in a
    settlement rail adapter (see rails.py) and stores its reference here.
    """
    __tablename__ = "bw_transfers"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    wallet_id: Mapped[str] = mapped_column(String, ForeignKey("bw_wallets.id"), index=True)
    direction: Mapped[str] = mapped_column(String(30))  # settle_down|convert|pledge_up
    from_layer: Mapped[str] = mapped_column(String(30))
    to_layer: Mapped[str] = mapped_column(String(30))
    holding_id: Mapped[str | None] = mapped_column(String, ForeignKey("bw_holdings.id"), nullable=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rail: Mapped[str] = mapped_column(String(50), default="simulated")
    external_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="settled")  # settled|pending|failed
