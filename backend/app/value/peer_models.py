import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base

PEER_STATUS = ("active", "suspended")


def _uuid() -> str:
    return str(uuid.uuid4())


class Peer(Base):
    """Another node this one will talk to (WP-012 §10, step 3).

    Peering is by relationship, not open: a node answers and forwards only for peers it
    has deliberately added, each with its own trust weight and rate limit.
    """
    __tablename__ = "vm_peers"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    node_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    base_url: Mapped[str | None] = mapped_column(String(300), nullable=True)  # None: inbound only
    public_key: Mapped[str] = mapped_column(String(100))                      # base64url Ed25519
    trust_weight: Mapped[float] = mapped_column(Float, default=0.5)           # 0..1, this hop's weight
    status: Mapped[str] = mapped_column(String(20), default="active")
    max_queries_per_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    added_by: Mapped[str | None] = mapped_column(String(400), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class QueryLog(Base):
    """What was asked of this node, by whom, and what it answered.

    The paper's requirement: a node can see who has been asking it what. Commitments are
    recorded, not contents: the log does not reveal what was being looked for either.
    """
    __tablename__ = "vm_query_log"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    direction: Mapped[str] = mapped_column(String(20))       # inbound|outbound|local
    peer_node_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    asked_by: Mapped[str | None] = mapped_column(String(400), nullable=True)
    commitment: Mapped[str] = mapped_column(String(64), index=True)
    ttl: Mapped[int] = mapped_column(Integer, default=0)
    path: Mapped[list] = mapped_column(JSON, default=list)
    matched: Mapped[str] = mapped_column(String(10), default="unknown")
    results: Mapped[int] = mapped_column(Integer, default=0)
