"""Derived records: reproducible by construction, bounded by review capacity."""
import hashlib
import json
from datetime import timedelta

from sqlalchemy.orm import Session

from app.agents.config import load_agent_rules
from app.agents.models import Agent, DerivedRecord, Recomputation
from app.core.time import utcnow


class AgentError(ValueError):
    pass


class AgentForbidden(PermissionError):
    pass


class QueueFull(RuntimeError):
    """The agent's unreviewed queue is full: writes pause rather than review being skipped."""


def canonical_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def unreviewed_count(db: Session, agent: Agent) -> int:
    return db.query(DerivedRecord).filter(
        DerivedRecord.agent_id == agent.id, DerivedRecord.status == "unreviewed"
    ).count()


def ceiling_for(agent: Agent) -> int:
    return int(agent.max_unreviewed or load_agent_rules().max_unreviewed_records)


def queue_state(db: Session, agent: Agent) -> dict:
    used = unreviewed_count(db, agent)
    ceiling = ceiling_for(agent)
    return {
        "unreviewed": used,
        "ceiling": ceiling,
        "remaining": max(ceiling - used, 0),
        "writes_paused": used >= ceiling,
        "note": "Writes pause when the unreviewed queue is full. The queue stops; the review is never skipped.",
    }


def record_derived(db: Session, agent: Agent, *, kind: str, subject_ref: str, statement: str,
                   inputs: dict, output: dict, method: str, confidence: float | None) -> DerivedRecord:
    rules = load_agent_rules()
    if agent.status != "active":
        raise AgentForbidden(f"agent is {agent.status}")
    if kind not in rules.record_kinds:
        raise AgentError(f"unknown record kind '{kind}'; allowed: {sorted(rules.record_kinds)}")
    if not (rules.scopes_for_kind(kind) & set(agent.scopes or [])):
        raise AgentForbidden(f"recording '{kind}' needs one of these scopes: {sorted(rules.scopes_for_kind(kind))}")
    if len(json.dumps(inputs, default=str)) > rules.max_input_bytes:
        raise AgentError(f"inputs exceed {rules.max_input_bytes} bytes; reference the records instead of copying them")

    since = utcnow() - timedelta(hours=1)
    if db.query(DerivedRecord).filter(DerivedRecord.agent_id == agent.id, DerivedRecord.created_at >= since).count() >= rules.max_records_per_hour:
        raise QueueFull(f"rate limit reached: {rules.max_records_per_hour} records an hour")
    if unreviewed_count(db, agent) >= ceiling_for(agent):
        raise QueueFull(
            f"unreviewed queue is full ({ceiling_for(agent)}). Writes pause until a reviewer works through it."
        )

    rec = DerivedRecord(
        agent_id=agent.id, kind=kind, subject_ref=subject_ref, statement=statement,
        inputs=inputs, inputs_hash=canonical_hash(inputs), output=output, output_hash=canonical_hash(output),
        method=method, confidence=confidence,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def review_record(db: Session, rec: DerivedRecord, *, accept: bool, note: str, reviewer_subject: str) -> DerivedRecord:
    if rec.status != "unreviewed":
        raise AgentError(f"record is already {rec.status}")
    rec.status = "confirmed" if accept else "rejected"
    rec.review_note = note
    rec.reviewed_by = reviewer_subject
    rec.reviewed_at = utcnow()
    db.commit()
    db.refresh(rec)
    return rec


def recompute(db: Session, rec: DerivedRecord, *, output: dict, method: str, by_subject: str,
              note: str | None) -> dict:
    """Rerun someone else's derivation. A mismatch supersedes the original automatically."""
    if by_subject == _agent_did(db, rec):
        raise AgentForbidden("a record must be recomputed by someone other than the agent that produced it")
    out_hash = canonical_hash(output)
    matched = out_hash == rec.output_hash
    r = Recomputation(record_id=rec.id, by_subject=by_subject, output=output, output_hash=out_hash,
                      method=method, result="matched" if matched else "mismatched", note=note)
    db.add(r)
    rec.recompute_status = "matched" if matched else "mismatched"
    superseded = False
    if not matched and load_agent_rules().on_mismatch == "supersede":
        rec.status = "superseded"
        superseded = True
    db.commit()
    db.refresh(rec)
    db.refresh(r)
    return {"recomputation": r, "record": rec, "matched": matched, "superseded": superseded}


def _agent_did(db: Session, rec: DerivedRecord) -> str | None:
    a = db.get(Agent, rec.agent_id)
    return a.did if a else None
