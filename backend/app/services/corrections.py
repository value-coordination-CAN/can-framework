"""Right to correction: people dispute entries about them; an independent reviewer resolves.

Corrections never overwrite history. A corrected or removed entry is marked superseded and
stops counting; a correction is recorded as a new attested entry that points back to it.
Disputed entries keep counting until resolved, so disputing cannot be used to game a score.
"""
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.db.models import EntryDispute, LedgerEntry, User

OUTCOMES = {"corrected", "removed", "rejected"}


class CorrectionError(ValueError):
    pass


class CorrectionForbidden(PermissionError):
    pass


def open_dispute(db: Session, entry: LedgerEntry, me: User, reason: str, proposed_value: float | None) -> EntryDispute:
    if entry.user_id != me.id:
        raise CorrectionForbidden("you can only dispute entries about yourself")
    if entry.superseded_at is not None:
        raise CorrectionError("this entry has already been superseded")
    if entry.self_reported:
        raise CorrectionError("self-reported entries can be deleted directly instead of disputed")
    if db.query(EntryDispute).filter(EntryDispute.entry_id == entry.id, EntryDispute.status == "open").first():
        raise CorrectionError("a dispute for this entry is already open")
    d = EntryDispute(entry_id=entry.id, user_id=me.id, reason=reason, proposed_value=proposed_value)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def resolve_dispute(
    db: Session,
    dispute: EntryDispute,
    *,
    outcome: str,
    note: str,
    corrected_value: float | None,
    reviewer_subject: str,
    reviewer_user_id: str | None,
) -> EntryDispute:
    if outcome not in OUTCOMES:
        raise CorrectionError(f"outcome must be one of {sorted(OUTCOMES)}")
    if dispute.status != "open":
        raise CorrectionError("dispute already resolved")
    entry = db.get(LedgerEntry, dispute.entry_id)
    if reviewer_user_id is not None and reviewer_user_id == dispute.user_id:
        raise CorrectionForbidden("reviewers cannot resolve disputes about themselves")
    if entry is not None and entry.attester_subject == reviewer_subject:
        raise CorrectionForbidden("a dispute must be resolved by someone other than the original attester")
    if outcome == "corrected" and corrected_value is None:
        raise CorrectionError("corrected_value is required when the outcome is 'corrected'")

    now = utcnow()
    if entry is not None and outcome in {"corrected", "removed"}:
        entry.superseded_at = now
        entry.superseded_reason = f"{outcome} via dispute {dispute.id}"
        if outcome == "corrected":
            fixed = LedgerEntry(
                user_id=entry.user_id,
                ledger_type=entry.ledger_type,
                metric=entry.metric,
                value=corrected_value,
                evidence_ref=f"correction:{dispute.id}",
                attester_subject=reviewer_subject,
                self_reported=False,
                supersedes_id=entry.id,
            )
            db.add(fixed)
            db.flush()
            dispute.corrected_entry_id = fixed.id

    dispute.status = outcome
    dispute.resolution_note = note
    dispute.resolved_by = reviewer_subject
    dispute.resolved_at = now
    db.commit()
    db.refresh(dispute)
    return dispute


def delete_self_reported(db: Session, entry: LedgerEntry, me: User) -> None:
    if entry.user_id != me.id:
        raise CorrectionForbidden("you can only delete entries about yourself")
    if not entry.self_reported:
        raise CorrectionError("attested entries cannot be deleted; open a dispute instead")
    db.delete(entry)
    db.commit()
