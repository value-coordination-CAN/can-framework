import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base

AGENT_STATUS = ("active", "suspended", "revoked")
RECORD_STATUS = ("unreviewed", "confirmed", "rejected", "superseded")
RECOMPUTE_STATUS = ("unchecked", "matched", "mismatched")


def _uuid() -> str:
    return str(uuid.uuid4())


class Agent(Base):
    """An agent identity. No steward, no write access."""
    __tablename__ = "ag_agents"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    did: Mapped[str] = mapped_column(String(400), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    steward_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    # Published in the open register, so anyone affected can reach whoever answers for the agent.
    contact: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # The steward's own name is published only if they choose. The contact is not optional.
    steward_name_public: Mapped[bool] = mapped_column(Boolean, default=False)
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="active")
    max_unreviewed: Mapped[int | None] = mapped_column(nullable=True)  # overrides the default ceiling
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class DerivedRecord(Base):
    """Something an agent worked out from records, not something it witnessed.

    It carries its inputs, its method and its output, so anyone can recompute it.
    """
    __tablename__ = "ag_derived_records"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("ag_agents.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    subject_ref: Mapped[str] = mapped_column(String(200), index=True)  # e.g. "asset:<id>", "user:<id>"
    statement: Mapped[str] = mapped_column(Text)  # what it says, in words a person can read
    inputs: Mapped[dict] = mapped_column(JSON)
    inputs_hash: Mapped[str] = mapped_column(String(64))
    output: Mapped[dict] = mapped_column(JSON)
    output_hash: Mapped[str] = mapped_column(String(64), index=True)
    method: Mapped[str] = mapped_column(String(300))  # model or code version, enough to reproduce
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="unreviewed")
    recompute_status: Mapped[str] = mapped_column(String(20), default="unchecked")
    reviewed_by: Mapped[str | None] = mapped_column(String(400), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    superseded_by_id: Mapped[str | None] = mapped_column(String, ForeignKey("ag_derived_records.id"), nullable=True)


class Recomputation(Base):
    """An independent rerun of a derived record. A mismatch supersedes the original."""
    __tablename__ = "ag_recomputations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    record_id: Mapped[str] = mapped_column(String, ForeignKey("ag_derived_records.id"), index=True)
    by_subject: Mapped[str] = mapped_column(String(400))  # the agent DID or human subject that reran it
    output: Mapped[dict] = mapped_column(JSON)
    output_hash: Mapped[str] = mapped_column(String(64))
    method: Mapped[str] = mapped_column(String(300))
    result: Mapped[str] = mapped_column(String(20))  # matched|mismatched
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
