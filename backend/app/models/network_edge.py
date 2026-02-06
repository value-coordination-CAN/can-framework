from sqlalchemy import Column, String, Float, DateTime
from app.db.base import Base

class NetworkEdge(Base):
    __tablename__ = "network_edges"

    id = Column(String, primary_key=True, index=True)
    source_user_id = Column(String, index=True, nullable=False)

    target_user_id = Column(String, index=True, nullable=True)
    target_external_id = Column(String, index=True, nullable=True)

    edge_type = Column(String, nullable=False, default="connected")
    weight = Column(Float, nullable=False, default=0.30)

    evidence_ref = Column(String, nullable=True)
    source_system = Column(String, nullable=False, default="manual")

    # optional display_name for UI/debug (do not rely on it as identifier)
    display_name = Column(String, nullable=True)

    created_at = Column(DateTime, nullable=False)
