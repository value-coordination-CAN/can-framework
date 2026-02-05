import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Float, ForeignKey, Text, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

def _uuid() -> str:
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    display_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)

class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    ledger_type: Mapped[str] = mapped_column(String(50))  # contribution|reliability|care
    metric: Mapped[str] = mapped_column(String(100))
    value: Mapped[float] = mapped_column(Float)
    evidence_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)

class ScoreSnapshot(Base):
    __tablename__ = "score_snapshots"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    contribution_score: Mapped[float] = mapped_column(Float)
    reliability_score: Mapped[float] = mapped_column(Float)
    care_score: Mapped[float] = mapped_column(Float)
    overall_score: Mapped[float] = mapped_column(Float)

class AllocationRequest(Base):
    __tablename__ = "allocation_requests"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    pool: Mapped[str] = mapped_column(String(100))  # housing|transport|food|energy|learning
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="submitted")
    priority_score: Mapped[float | None] = mapped_column(Float, nullable=True)

class Appeal(Base):
    __tablename__ = "appeals"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    request_id: Mapped[str] = mapped_column(String, ForeignKey("allocation_requests.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="open")

class DIDChallenge(Base):
    __tablename__ = "did_challenges"
    challenge: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False)

class DIDSession(Base):
    __tablename__ = "did_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    did: Mapped[str] = mapped_column(String(400), index=True)
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False)
    assurance_level: Mapped[str] = mapped_column(String(50), default="A1_DID_ONLY")
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)

class SubjectLink(Base):
    __tablename__ = "subject_links"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    did: Mapped[str] = mapped_column(String(400), unique=True, index=True)
    oidc_sub: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    assurance_level: Mapped[str] = mapped_column(String(50), default="A1_DID_ONLY")
