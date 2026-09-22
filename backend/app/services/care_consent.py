from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.db.models import CareConsent, LedgerEntry
from app.services.ledger_config import load_ledger_config


def active_consented_factors(db: Session, user_id: str) -> set[str]:
    rows = db.query(CareConsent).filter(
        CareConsent.user_id == user_id,
        CareConsent.revoked_at.is_(None),
    ).all()
    return {r.factor for r in rows}


def set_care_consent(db: Session, user_id: str, factors: set[str]) -> dict:
    """Make the consented set exactly `factors`. Revoking a factor deletes its care entries."""
    care = load_ledger_config().ledgers["care"]
    unknown = factors - care.opt_in_required
    if unknown:
        raise ValueError(f"not opt-in care factors: {sorted(unknown)}")

    now = utcnow()
    current = {
        r.factor: r
        for r in db.query(CareConsent).filter(CareConsent.user_id == user_id).all()
    }
    granted, revoked = [], []
    for f in factors:
        row = current.get(f)
        if row is None:
            db.add(CareConsent(user_id=user_id, factor=f, granted_at=now))
            granted.append(f)
        elif row.revoked_at is not None:
            row.revoked_at = None
            row.granted_at = now
            granted.append(f)
    deleted = 0
    for f, row in current.items():
        if f not in factors and row.revoked_at is None:
            row.revoked_at = now
            revoked.append(f)
            deleted += db.query(LedgerEntry).filter(
                LedgerEntry.user_id == user_id,
                LedgerEntry.ledger_type == "care",
                LedgerEntry.metric == f,
            ).delete(synchronize_session=False)
    db.commit()
    return {
        "consented_factors": sorted(active_consented_factors(db, user_id)),
        "granted": sorted(granted),
        "revoked": sorted(revoked),
        "entries_deleted": deleted,
    }
