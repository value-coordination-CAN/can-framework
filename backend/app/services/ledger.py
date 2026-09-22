from sqlalchemy.orm import Session

from app.db.models import LedgerEntry
from app.services.care_consent import active_consented_factors
from app.services.ledger_config import load_ledger_config


class LedgerValidationError(ValueError):
    pass


class ConsentRequiredError(PermissionError):
    pass


def create_ledger_entry(
    db: Session,
    *,
    user_id: str,
    ledger_type: str,
    metric: str,
    value: float,
    evidence_ref: str | None,
    attester_subject: str,
    self_reported: bool,
) -> LedgerEntry:
    ledger = load_ledger_config().ledgers.get(ledger_type)
    if ledger is None:
        raise LedgerValidationError(f"unknown ledger type: {ledger_type}")
    if metric not in ledger.weights:
        raise LedgerValidationError(f"unknown {ledger_type} metric '{metric}'; allowed: {list(ledger.metrics)}")
    if metric in ledger.opt_in_required and metric not in active_consented_factors(db, user_id):
        raise ConsentRequiredError(f"care factor '{metric}' requires the person's explicit consent")

    entry = LedgerEntry(
        user_id=user_id,
        ledger_type=ledger_type,
        metric=metric,
        value=value,
        evidence_ref=evidence_ref,
        attester_subject=attester_subject,
        self_reported=self_reported,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
