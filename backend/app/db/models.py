import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # Authenticated subject (DID or OIDC sub) that owns this profile.
    subject: Mapped[str | None] = mapped_column(String(400), unique=True, index=True, nullable=True)
    display_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    ledger_type: Mapped[str] = mapped_column(String(50))  # contribution|reliability|care
    metric: Mapped[str] = mapped_column(String(100))
    value: Mapped[float] = mapped_column(Float)  # normalised 0..1
    evidence_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Who recorded it. Self-reported entries are kept but do not count towards priority.
    attester_subject: Mapped[str | None] = mapped_column(String(400), nullable=True)
    self_reported: Mapped[bool] = mapped_column(Boolean, default=True)
    # Corrections never overwrite: the old entry is superseded (and stops counting),
    # and a corrected entry points back at it.
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    superseded_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    supersedes_id: Mapped[str | None] = mapped_column(String, ForeignKey("ledger_entries.id"), nullable=True)

    @property
    def status(self) -> str:
        return "superseded" if self.superseded_at is not None else "active"


class EntryDispute(Base):
    """A person disputes an entry recorded about them (right to correction)."""
    __tablename__ = "entry_disputes"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    entry_id: Mapped[str] = mapped_column(String, ForeignKey("ledger_entries.id"), index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    proposed_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="open")  # open|corrected|removed|rejected
    resolved_by: Mapped[str | None] = mapped_column(String(400), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_entry_id: Mapped[str | None] = mapped_column(String, ForeignKey("ledger_entries.id"), nullable=True)


class DeletionRecord(Base):
    """Audit trace of an account deletion. Holds counts only, no personal data."""
    __tablename__ = "deletion_records"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    deleted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    counts: Mapped[dict] = mapped_column(JSON)


class CareConsent(Base):
    """Explicit, revocable opt-in for a sensitive care factor (special-category data)."""
    __tablename__ = "care_consents"
    __table_args__ = (UniqueConstraint("user_id", "factor", name="uq_care_consents_user_factor"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    factor: Mapped[str] = mapped_column(String(100))
    granted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ScoreSnapshot(Base):
    __tablename__ = "score_snapshots"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    contribution_score: Mapped[float] = mapped_column(Float)
    reliability_score: Mapped[float] = mapped_column(Float)
    care_score: Mapped[float] = mapped_column(Float)
    overall_score: Mapped[float] = mapped_column(Float)
    explanation: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AllocationRequest(Base):
    __tablename__ = "allocation_requests"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    pool: Mapped[str] = mapped_column(String(100))  # housing|transport|food|energy|learning
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="submitted")  # submitted|approved|declined
    priority_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_snapshot_id: Mapped[str | None] = mapped_column(String, ForeignKey("score_snapshots.id"), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(400), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class Appeal(Base):
    __tablename__ = "appeals"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    request_id: Mapped[str] = mapped_column(String, ForeignKey("allocation_requests.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="open")  # open|upheld|rejected
    resolved_by: Mapped[str | None] = mapped_column(String(400), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class DIDChallenge(Base):
    __tablename__ = "did_challenges"
    challenge: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False)


class DIDSession(Base):
    __tablename__ = "did_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    did: Mapped[str] = mapped_column(String(400), index=True)
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False)
    assurance_level: Mapped[str] = mapped_column(String(50), default="A1_DID_ONLY")
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class SubjectLink(Base):
    __tablename__ = "subject_links"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    did: Mapped[str] = mapped_column(String(400), unique=True, index=True)
    oidc_sub: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    assurance_level: Mapped[str] = mapped_column(String(50), default="A1_DID_ONLY")
