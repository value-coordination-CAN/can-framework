import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base

ITEM_TYPES = ("capacity", "need")


def _uuid() -> str:
    return str(uuid.uuid4())


class MapItem(Base):
    """What a node has spare, and what it lacks (WP-012 §1).

    `discoverable` is opt-in per item: an item is findable by other nodes only if its
    holder says so, and only ever through a commitment, never by listing.
    """
    __tablename__ = "vm_items"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    holder_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    item_type: Mapped[str] = mapped_column(String(20))            # capacity|need
    item_class: Mapped[str] = mapped_column(String(100), index=True)  # e.g. covered_workshop
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    region: Mapped[str] = mapped_column(String(50), index=True)   # coarse: e.g. GCC-E, UK-NW
    available_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    available_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    asset_id: Mapped[str | None] = mapped_column(String, ForeignKey("va_assets.id"), nullable=True)
    attributes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    discoverable: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|matched|closed
