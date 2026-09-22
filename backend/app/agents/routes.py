"""Agent integration API.

Registration and revocation are done by a human steward. Sign-in proves the agent's DID.
Everything an agent records is a derivation: reproducible, bounded by review capacity, and
attributable to the agent and its steward.
"""
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.agents import service
from app.agents.auth import ROLE_AGENT, get_current_agent
from app.agents.config import load_agent_rules
from app.agents.models import Agent, DerivedRecord, Recomputation
from app.agents.schemas import (
    AgentOut,
    AgentRegister,
    AgentUpdate,
    AgentVerifyIn,
    AgentVerifyOut,
    PublicAgentOut,
    DerivedRecordIn,
    DerivedRecordOut,
    RecomputationOut,
    RecomputeIn,
    ReviewIn,
)
from app.core.auth import (
    ROLE_ADMIN,
    ROLE_AUDITOR,
    ROLE_REVIEWER,
    ROLE_USER,
    get_current_principal,
    get_current_user,
    has_any_role,
    require_any_role,
)
from app.core.config import settings
from app.core.did_key import DIDFormatError, verify_did_key_ed25519
from app.core.did_session import mint_did_session_token
from app.core.time import utcnow
from app.db.models import DIDChallenge, DIDSession, User
from app.db.session import get_db

router = APIRouter()


def _agent(db: Session, agent_id: str) -> Agent:
    a = db.get(Agent, agent_id)
    if not a:
        raise HTTPException(status_code=404, detail="agent not found")
    return a


def _steward_or_oversight(a: Agent, me: User | None, principal: dict) -> None:
    if me is not None and a.steward_user_id == me.id:
        return
    if has_any_role(principal, ROLE_REVIEWER, ROLE_ADMIN, ROLE_AUDITOR):
        return
    raise HTTPException(status_code=403, detail="only the steward and oversight roles can do this")


@router.get("/rules")
def rules():
    """The public terms agents work under: record kinds, scopes, limits and holdings."""
    r = load_agent_rules()
    return {
        "record_kinds": r.record_kinds,
        "scopes": r.scopes,
        "kind_scopes": {k: sorted(r.scopes_for_kind(k)) for k in r.record_kinds},
        "limits": {
            "max_unreviewed_records": r.max_unreviewed_records,
            "max_records_per_hour": r.max_records_per_hour,
            "max_input_bytes": r.max_input_bytes,
            "max_unreviewed_per_steward": r.max_unreviewed_per_steward,
            "max_agents_per_steward": r.max_agents_per_steward,
        },
        "holdings": r.holdings,
        "recomputation": {"on_mismatch": r.on_mismatch},
        "principles": [
            "Agents derive; they do not witness. No agent may attest to first-hand fact.",
            "Every agent answers to a named steward. No steward, no write access.",
            "Every agent is listed in the open register at /agents/register, with a contact, "
            "readable by anyone without an account.",
            "Every derived record is reproducible from its stated inputs.",
            "A record that fails recomputation is superseded automatically.",
            "Writes pause when the unreviewed queue is full; the review is never skipped.",
            "Ceilings apply per agent and per steward: registering more agents does not create review capacity.",
            "Agents may hold mandates. They never hold entitlements to what people need.",
        ],
    }


# --- the open register: no account needed --------------------------------------------

@router.get("/register", response_model=list[PublicAgentOut])
def public_register(
    q: str | None = Query(None, max_length=200, description="Match on name, model or DID"),
    status: str | None = Query(None, pattern="^(active|suspended|revoked|no_steward)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Every agent that can write to CAN, and who answers for it.

    Open to anyone, without an account: a person affected by an agent's work should not
    need standing in the system to find out who is responsible for it. Revoked agents stay
    listed, because accountability outlives the mandate.
    """
    query = db.query(Agent)
    if q:
        like = f"%{q}%"
        query = query.filter(Agent.name.ilike(like) | Agent.model.ilike(like) | Agent.did.ilike(like))
    entries = [service.public_entry(db, a) for a in query.order_by(Agent.created_at.desc()).offset(offset).limit(limit)]
    if status:
        entries = [e for e in entries if e["status"] == status]
    return entries


@router.get("/register/{agent_id}", response_model=PublicAgentOut)
def public_register_entry(agent_id: str, db: Session = Depends(get_db)):
    """One agent's public entry. What it wrote, and about whom, is not published here:
    to read or challenge a particular record you sign in and use /agents/records."""
    return service.public_entry(db, _agent(db, agent_id))


# --- registration, by a human steward ------------------------------------------------

@router.post("/", response_model=AgentOut)
def register(payload: AgentRegister, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Register an agent you will answer for. You become its steward."""
    r = load_agent_rules()
    unknown = set(payload.scopes) - set(r.scopes)
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown scopes {sorted(unknown)}; allowed: {sorted(r.scopes)}")
    if db.query(Agent).filter(Agent.did == payload.did).first():
        raise HTTPException(status_code=409, detail="this DID is already registered")
    if db.query(User).filter(User.subject == payload.did).first():
        raise HTTPException(status_code=409, detail="this DID belongs to a person's profile, not an agent")
    try:
        service.check_can_register(db, me.id)
    except service.AgentForbidden as e:
        raise HTTPException(status_code=403, detail=str(e))
    a = Agent(steward_user_id=me.id, **payload.model_dump())
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@router.get("/", response_model=list[AgentOut])
def list_agents(mine: bool = Query(True, description="Only agents you steward"),
                db: Session = Depends(get_db), me: User = Depends(get_current_user),
                principal=Depends(get_current_principal)):
    q = db.query(Agent)
    if mine or not has_any_role(principal, ROLE_REVIEWER, ROLE_ADMIN, ROLE_AUDITOR):
        q = q.filter(Agent.steward_user_id == me.id)
    return q.order_by(Agent.created_at).all()


def _update_agent(agent_id: str, payload: AgentUpdate, db: Session, me: User, principal: dict) -> Agent:
    a = _agent(db, agent_id)
    if a.steward_user_id != me.id and not has_any_role(principal, ROLE_ADMIN):
        raise HTTPException(status_code=403, detail="only the steward (or an admin) can change an agent")
    r = load_agent_rules()
    if payload.scopes is not None:
        unknown = set(payload.scopes) - set(r.scopes)
        if unknown:
            raise HTTPException(status_code=422, detail=f"unknown scopes {sorted(unknown)}")
        a.scopes = payload.scopes
    if payload.max_unreviewed is not None:
        a.max_unreviewed = payload.max_unreviewed
    if payload.contact is not None:
        a.contact = payload.contact
    if payload.steward_name_public is not None:
        a.steward_name_public = payload.steward_name_public
    if payload.status is not None:
        a.status = payload.status
        a.revoked_reason = payload.reason
        if payload.status in {"revoked", "suspended"}:
            a.revoked_at = utcnow()
            # end any live sessions for this agent
            db.query(DIDSession).filter(DIDSession.did == a.did, DIDSession.is_revoked.is_(False)).update(
                {DIDSession.is_revoked: True}, synchronize_session=False)
    db.commit()
    db.refresh(a)
    return a


# --- agent sign-in --------------------------------------------------------------------

@router.post("/auth/verify", response_model=AgentVerifyOut)
def agent_verify(payload: AgentVerifyIn, db: Session = Depends(get_db)):
    """Prove the agent's DID against a challenge from GET /auth/did/challenge."""
    rec = db.get(DIDChallenge, payload.challenge)
    if not rec:
        raise HTTPException(status_code=400, detail="unknown challenge")
    expired = int(time.time()) > int(rec.expires_at)
    db.delete(rec)
    db.commit()
    if expired:
        raise HTTPException(status_code=400, detail="expired challenge")

    agent = db.query(Agent).filter(Agent.did == payload.did).first()
    if agent is None:
        raise HTTPException(status_code=403, detail="unknown agent; a steward must register this DID first")
    if agent.status != "active":
        raise HTTPException(status_code=403, detail=f"agent is {agent.status}")
    if db.get(User, agent.steward_user_id) is None:
        raise HTTPException(status_code=403, detail="agent has no steward: write access withdrawn")

    try:
        ok = verify_did_key_ed25519(did=payload.did, message=payload.challenge.encode("utf-8"),
                                    signature_b64url=payload.signature_b64url)
    except DIDFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=401, detail="invalid did proof")

    ttl = settings.CAN_DID_SESSION_TTL_SECONDS
    session = DIDSession(did=agent.did, expires_at=int(time.time()) + ttl, assurance_level="A1_AGENT")
    db.add(session)
    db.commit()
    db.refresh(session)
    token = mint_did_session_token(agent.did, session.id, roles=[ROLE_AGENT], assurance_level="A1_AGENT")
    return {
        "access_token": token,
        "expires_in": ttl,
        "agent_id": agent.id,
        "steward_user_id": agent.steward_user_id,
        "scopes": agent.scopes or [],
        "queue": service.queue_state(db, agent),
    }


@router.get("/me/queue")
def my_queue(db: Session = Depends(get_db), agent: Agent = Depends(get_current_agent)):
    """How much room is left before writes pause, for this agent and for its steward.
    Check this before a batch."""
    return {"agent_id": agent.id, "scopes": agent.scopes, **service.queue_state(db, agent)}


@router.get("/steward/queue")
def steward_queue(db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """What you have left to review across every agent you steward."""
    return {"steward_user_id": me.id, **service.steward_queue_state(db, me.id)}


# --- derived records ------------------------------------------------------------------

@router.post("/records", response_model=DerivedRecordOut, status_code=201)
def create_record(payload: DerivedRecordIn, db: Session = Depends(get_db), agent: Agent = Depends(get_current_agent)):
    """Record a derivation. Not an observation: agents derive, they do not witness."""
    try:
        return service.record_derived(db, agent, **payload.model_dump())
    except service.QueueFull as e:
        raise HTTPException(status_code=429, detail=str(e), headers={"Retry-After": "3600"})
    except service.AgentForbidden as e:
        raise HTTPException(status_code=403, detail=str(e))
    except service.AgentError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/records", response_model=list[DerivedRecordOut])
def list_records(
    agent_id: str | None = None,
    subject_ref: str | None = None,
    status: str | None = Query(None, pattern="^(unreviewed|confirmed|rejected|superseded)$"),
    db: Session = Depends(get_db),
    principal=Depends(require_any_role(ROLE_USER, ROLE_AGENT, ROLE_AUDITOR)),
):
    """Anyone signed in can read derived records: they are claims about records, open to challenge."""
    q = db.query(DerivedRecord)
    if agent_id:
        q = q.filter(DerivedRecord.agent_id == agent_id)
    if subject_ref:
        q = q.filter(DerivedRecord.subject_ref == subject_ref)
    if status:
        q = q.filter(DerivedRecord.status == status)
    return q.order_by(DerivedRecord.created_at.desc()).limit(200).all()


@router.get("/records/{record_id}", response_model=DerivedRecordOut)
def get_record(record_id: str, db: Session = Depends(get_db),
               principal=Depends(require_any_role(ROLE_USER, ROLE_AGENT, ROLE_AUDITOR))):
    rec = db.get(DerivedRecord, record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="record not found")
    return rec


@router.post("/records/{record_id}/review", response_model=DerivedRecordOut)
def review(record_id: str, payload: ReviewIn, db: Session = Depends(get_db),
           me: User = Depends(get_current_user), principal=Depends(get_current_principal)):
    """A human confirms or rejects. This is what frees the agent's queue."""
    rec = db.get(DerivedRecord, record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="record not found")
    agent = _agent(db, rec.agent_id)
    if not has_any_role(principal, ROLE_REVIEWER, ROLE_ADMIN) and agent.steward_user_id != me.id:
        raise HTTPException(status_code=403, detail="only a reviewer or the agent's steward can review its records")
    try:
        return service.review_record(db, rec, accept=payload.accept, note=payload.note, reviewer_subject=principal["sub"])
    except service.AgentError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/records/{record_id}/recompute")
def recompute(record_id: str, payload: RecomputeIn, db: Session = Depends(get_db),
              principal=Depends(require_any_role(ROLE_USER, ROLE_AGENT, ROLE_REVIEWER, ROLE_AUDITOR))):
    """Rerun the derivation from the record's stated inputs and submit what you got.
    A mismatch supersedes the original automatically: no argument, no authority needed."""
    rec = db.get(DerivedRecord, record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="record not found")
    try:
        result = service.recompute(db, rec, output=payload.output, method=payload.method,
                                   by_subject=principal["sub"], note=payload.note)
    except service.AgentForbidden as e:
        raise HTTPException(status_code=403, detail=str(e))
    return {
        "matched": result["matched"],
        "superseded": result["superseded"],
        "record": DerivedRecordOut.model_validate(result["record"]).model_dump(mode="json"),
        "recomputation": RecomputationOut.model_validate(result["recomputation"]).model_dump(mode="json"),
    }


@router.get("/records/{record_id}/recomputations", response_model=list[RecomputationOut])
def list_recomputations(record_id: str, db: Session = Depends(get_db),
                        principal=Depends(require_any_role(ROLE_USER, ROLE_AGENT, ROLE_AUDITOR))):
    return db.query(Recomputation).filter(Recomputation.record_id == record_id).order_by(Recomputation.created_at).all()


# --- one agent (declared last: these paths would otherwise shadow /records and /rules) ---

@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user),
              principal=Depends(get_current_principal)):
    a = _agent(db, agent_id)
    _steward_or_oversight(a, me, principal)
    return a


@router.patch("/{agent_id}", response_model=AgentOut)
def update_agent(agent_id: str, payload: AgentUpdate, db: Session = Depends(get_db),
                 me: User = Depends(get_current_user), principal=Depends(get_current_principal)):
    """Change scopes or the queue ceiling, suspend, or revoke. Revoking is immediate."""
    return _update_agent(agent_id, payload, db, me, principal)
