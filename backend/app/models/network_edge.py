import uuid

from sqlalchemy import Column, DateTime, Float, String

from app.core.time import utcnow
from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class NetworkEdge(Base):
    __tablename__ = "network_edges"

    id = Column(String, primary_key=True, index=True, default=_uuid)
    source_user_id = Column(String, index=True, nullable=False)

    target_user_id = Column(String, index=True, nullable=True)
    target_external_id = Column(String, index=True, nullable=True)

    edge_type = Column(String, nullable=False, default="connected")
    weight = Column(Float, nullable=False, default=0.30)

    evidence_ref = Column(String, nullable=True)
    source_system = Column(String, nullable=False, default="manual")

    # Not populated for imported third parties (they have not consented to CAN).
    display_name = Column(String, nullable=True)

    created_at = Column(DateTime, nullable=False, default=utcnow)
