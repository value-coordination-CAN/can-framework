"""Derived records: reproducible by construction, bounded by review capacity."""
import hashlib
import json
from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.agents.config import load_agent_rules
from app.agents.models import Agent, DerivedRecord, Recomputation
from app.core.time import utcnow
from app.db.models import User


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


def steward_unreviewed_count(db: Session, steward_user_id: str) -> int:
    """Unreviewed records across every agent this steward answers for."""
    agent_ids = [a.id for a in db.query(Agent.id).filter(Agent.steward_user_id == steward_user_id)]
    if not agent_ids:
        return 0
    return db.query(DerivedRecord).filter(
        DerivedRecord.agent_id.in_(agent_ids), DerivedRecord.status == "unreviewed"
    ).count()


def steward_queue_state(db: Session, steward_user_id: str) -> dict:
    rules = load_agent_rules()
    used = steward_unreviewed_count(db, steward_user_id)
    ceiling = rules.max_unreviewed_per_steward
    agents = db.query(Agent).filter(Agent.steward_user_id == steward_user_id, Agent.status != "revoked").count()
    return {
        "unreviewed": used,
        "ceiling": ceiling,
        "remaining": max(ceiling - used, 0),
        "writes_paused": used >= ceiling,
        "agents": agents,
        "max_agents": rules.max_agents_per_steward,
        "note": "One steward cannot multiply throughput by registering more agents: "
                "these ceilings apply across all of them, because review capacity is what is scarce.",
    }


def queue_state(db: Session, agent: Agent) -> dict:
    used = unreviewed_count(db, agent)
    ceiling = ceiling_for(agent)
    return {
        "unreviewed": used,
        "ceiling": ceiling,
        "remaining": max(ceiling - used, 0),
        "writes_paused": used >= ceiling,
        "steward": steward_queue_state(db, agent.steward_user_id),
        "note": "Writes pause when the unreviewed queue is full. The queue stops; the review is never skipped.",
    }


def public_entry(db: Session, agent: Agent) -> dict:
    """The open register's view of an agent: who answers for it, and how its work has held up.

    It deliberately carries no subject references, statements, inputs or outputs: what an
    agent wrote, and about whom, is not public because an agent happens to be public.
    """
    rows = db.query(DerivedRecord.status, func.count(DerivedRecord.id)).filter(
        DerivedRecord.agent_id == agent.id
    ).group_by(DerivedRecord.status).all()
    by_status = {s: n for s, n in rows}
    mismatched = db.query(DerivedRecord).filter(
        DerivedRecord.agent_id == agent.id, DerivedRecord.recompute_status == "mismatched"
    ).count()
    checked = db.query(DerivedRecord).filter(
        DerivedRecord.agent_id == agent.id, DerivedRecord.recompute_status != "unchecked"
    ).count()
    steward = db.get(User, agent.steward_user_id)

    # Participation: what this agent has actually contributed, and how it has held up.
    # Counts and kinds only; never which records, or whose.
    by_kind = dict(db.query(DerivedRecord.kind, func.count(DerivedRecord.id)).filter(
        DerivedRecord.agent_id == agent.id).group_by(DerivedRecord.kind).all())
    first, last = db.query(func.min(DerivedRecord.created_at), func.max(DerivedRecord.created_at)).filter(
        DerivedRecord.agent_id == agent.id).one()
    subjects = db.query(func.count(func.distinct(DerivedRecord.subject_ref))).filter(
        DerivedRecord.agent_id == agent.id).scalar() or 0
    reviewed = by_status.get("confirmed", 0) + by_status.get("rejected", 0)
    participation = {
        "contributions_by_kind": by_kind,
        "subjects_contributed_to": subjects,
        "first_contribution": first,
        "latest_contribution": last,
        "confirmed_share": round(by_status.get("confirmed", 0) / reviewed, 3) if reviewed else None,
        "recomputation_pass_rate": round((checked - mismatched) / checked, 3) if checked else None,
        "value_accrues_to": "steward",
        "holds_entitlements": False,
        "note": "An agent's participation is visible and checkable. What it produces belongs to "
                "the steward who answers for it; an agent holds no entitlements of its own.",
    }
    return {
        "id": agent.id,
        "did": agent.did,
        "name": agent.name,
        "model": agent.model,
        "status": agent.status if steward is not None else "no_steward",
        "scopes": agent.scopes or [],
        "created_at": agent.created_at,
        "revoked_at": agent.revoked_at,
        "revoked_reason": agent.revoked_reason,
        "contact": agent.contact,
        "steward_name": steward.display_name if (steward is not None and agent.steward_name_public) else None,
        "records": {
            "total": sum(by_status.values()),
            "unreviewed": by_status.get("unreviewed", 0),
            "confirmed": by_status.get("confirmed", 0),
            "rejected": by_status.get("rejected", 0),
            "superseded": by_status.get("superseded", 0),
            "recomputed": checked,
            "failed_recomputation": mismatched,
        },
        "participation": participation,
    }


def check_can_register(db: Session, steward_user_id: str) -> None:
    rules = load_agent_rules()
    active = db.query(Agent).filter(Agent.steward_user_id == steward_user_id, Agent.status != "revoked").count()
    if active >= rules.max_agents_per_steward:
        raise AgentForbidden(
            f"you already steward {active} agents, the limit per steward is {rules.max_agents_per_steward}. "
            "Revoke one, or ask another person who can genuinely review their output to steward it."
        )


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
    if steward_unreviewed_count(db, agent.steward_user_id) >= rules.max_unreviewed_per_steward:
        raise QueueFull(
            f"your steward's unreviewed queue is full ({rules.max_unreviewed_per_steward} across all their agents). "
            "Registering more agents does not create more review capacity."
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
