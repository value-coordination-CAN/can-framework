"""From a committed introduction to a recorded stake (WP-012 §5 into WP-010 §3, §4).

An introduction ends with two parties agreeing. That agreement should not evaporate into
an email: it becomes a record, and where both parties are on the same node it becomes a
**contribution** or a **supplier agreement** directly, so the work earns participation or
access rather than only goodwill.

Across nodes, the agreement is carried as a signed document that each side stores and can
verify. It does **not** create a contribution on the far node, because a contributor there
would need a local identity that nobody has vouched for. What travels is the agreement;
what turns it into a stake is a local act by a local party, done deliberately.
"""
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.bridge.models import SOURCE_TYPES, Contribution, Project, SupplierAgreement
from app.core.config import settings
from app.core.time import utcnow
from app.db.base import Base
from app.db.models import User

from app.value.documents import AGREEMENT_PROFILE  # noqa: F401  (re-exported for the routes)

KINDS = ("contribution", "supply", "access")

# Which WP-010 funding source a kind of agreement becomes
SOURCE_FOR_KIND = {"contribution": "in_kind", "access": "pre_committed_use"}


def _uuid() -> str:
    return str(uuid.uuid4())


class AgreementRecord(Base):
    """What two parties agreed, on the node of each of them."""
    __tablename__ = "vm_agreements"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    introduction_id: Mapped[str | None] = mapped_column(String, nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    terms: Mapped[str] = mapped_column(Text)
    offer: Mapped[str | None] = mapped_column(Text, nullable=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    recorded_by: Mapped[str] = mapped_column(String(400))
    counterpart_node: Mapped[str | None] = mapped_column(String(100), nullable=True)
    counterpart_contact: Mapped[str | None] = mapped_column(String(300), nullable=True)
    document: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Where it became a stake, if it did
    linked_type: Mapped[str | None] = mapped_column(String(30), nullable=True)  # contribution|supplier_agreement
    linked_id: Mapped[str | None] = mapped_column(String, nullable=True)
    project_id: Mapped[str | None] = mapped_column(String, ForeignKey("bw_projects.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="recorded")  # recorded|linked


def build_agreement_document(record: AgreementRecord, parties: dict) -> dict:
    """A signed, verifiable statement of what was agreed, for the other node to keep."""
    from app.value.documents import _b64, _unb64, document_root
    from nacl.signing import SigningKey

    doc = {
        "header": {
            "profile": AGREEMENT_PROFILE,
            "document_id": uuid.uuid4().hex,
            "issued_at": utcnow().isoformat(),
            "node_id": settings.NODE_ID,
            "subject": {"correlation_id": record.correlation_id, "kind": record.kind},
            "parties": parties,
        },
        "items": [],
        "agreement": {
            "kind": record.kind, "terms": record.terms, "offer": record.offer,
            "value": record.value, "currency": record.currency,
        },
    }
    doc["root"] = document_root(doc)
    key = settings.NODE_SIGNING_KEY
    if key:
        sk = SigningKey(_unb64(key))
        doc["signature"] = {"alg": "ed25519", "node_id": settings.NODE_ID,
                            "public_key": _b64(bytes(sk.verify_key)),
                            "value": _b64(sk.sign(doc["root"].encode()).signature)}
    return doc


def link_locally(db: Session, record: AgreementRecord, *, project: Project, counterpart: User,
                 caller: User, source_type: str | None = None, cash_share: float = 1.0) -> dict:
    """Turn the agreement into a stake, where both parties are on this node.

    A contribution earns participation or access (WP-010 §3); a supply agreement sets the
    split between cash and a verified stake (WP-010 §4). Both are created as **proposals**:
    the sponsor still decides, and the supplier still chooses.
    """
    if project.sponsor_user_id != caller.id:
        raise PermissionError("only the project's sponsor can attach an agreement to it")
    if counterpart.id == caller.id:
        raise ValueError("an agreement needs two different parties")
    if record.status == "linked":
        raise ValueError("this agreement is already linked")

    if record.kind == "supply":
        agreement = SupplierAgreement(project_id=project.id, supplier_user_id=counterpart.id,
                                      scope=record.terms, cash_share=cash_share,
                                      participation_share=round(1 - cash_share, 6))
        db.add(agreement)
        db.flush()
        record.linked_type, record.linked_id = "supplier_agreement", agreement.id
        created = {"supplier_agreement_id": agreement.id, "cash_share": cash_share}
    else:
        source = source_type or SOURCE_FOR_KIND[record.kind]
        if source not in SOURCE_TYPES:
            raise ValueError(f"source_type must be one of {list(SOURCE_TYPES)}")
        contribution = Contribution(
            project_id=project.id, contributor_user_id=counterpart.id, source_type=source,
            description=record.terms, offered_value=record.value or 0.0,
            wants="access" if record.kind == "access" else "participation",
            access_terms={"from_agreement": record.id} if record.kind == "access" else None,
        )
        db.add(contribution)
        db.flush()
        record.linked_type, record.linked_id = "contribution", contribution.id
        created = {"contribution_id": contribution.id, "source_type": source,
                   "status": contribution.status}

    record.project_id = project.id
    record.status = "linked"
    db.commit()
    db.refresh(record)
    return created
