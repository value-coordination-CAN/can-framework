"""WP-010 bridge wallet API, and payment mandates for agents (WP-013)."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.agents.auth import ROLE_AGENT, get_current_agent
from app.agents.models import Agent
from app.bridge import service
from app.bridge.agent_payments import pay
from app.bridge.mandate_models import AgentPayment, PaymentMandate
from app.bridge.models import (
    HOLDING_KINDS,
    LAYERS,
    SOURCE_TYPES,
    BridgeTransfer,
    Contribution,
    Holding,
    Pledge,
    Project,
    SupplierAgreement,
    SupplierInvoice,
    Wallet,
)
from app.bridge.rails import DEFAULT_RAIL, RAILS, SimulatedRail, compliance_review_required
from app.bridge.schemas import (
    AgreementCreate,
    AgreementOut,
    AgreementResponseIn,
    ContributionCreate,
    ContributionDecisionIn,
    ContributionOut,
    InvoiceCreate,
    InvoiceOut,
    InvoiceVerifyIn,
    PledgeCreate,
    PledgeOut,
    ProjectCreate,
    ProjectOut,
    ProjectStatusIn,
    SettleIn,
    TransferOut,
)
from app.core.auth import (
    ROLE_ADMIN,
    ROLE_AUDITOR,
    ROLE_REVIEWER,
    ROLE_USER,
    current_user_or_none,
    get_current_principal,
    get_current_user,
    has_any_role,
    require_any_role,
)
from app.core.time import utcnow
from app.db.models import User
from app.db.session import get_db

router = APIRouter()


def _project(db: Session, project_id: str) -> Project:
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="project not found")
    return p


def _sponsor_only(p: Project, me: User) -> None:
    if p.sponsor_user_id != me.id:
        raise HTTPException(status_code=403, detail="only the project sponsor can do this")


def _holding(db: Session, holding_id: str, me: User) -> Holding:
    h = db.get(Holding, holding_id)
    wallet = service.get_or_create_wallet(db, me.id)
    if not h or h.wallet_id != wallet.id:
        raise HTTPException(status_code=404, detail="holding not found in your wallet")
    return h


def _wrap(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except service.BridgeForbidden as e:
        raise HTTPException(status_code=403, detail=str(e))
    except service.BridgeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/config")
def config(principal=Depends(get_current_principal)):
    """Layers, holding kinds, funding sources and which settlement rails are implemented."""
    return {
        "layers": list(LAYERS),
        "holding_kinds": HOLDING_KINDS,
        "source_types": list(SOURCE_TYPES),
        "rails": [
            {"name": name, "layer": rail.layer, "implemented": isinstance(rail, SimulatedRail),
             "default": name == DEFAULT_RAIL}
            for name, rail in RAILS.items()
        ],
        "reviews_before_issuing_units": compliance_review_required("in_kind", 0),
        "note": "Real fiat, tokenised-deposit, CBDC and offline rails are adapters to be implemented; "
                "the simulated rail records movements without moving money.",
    }


# --- wallet -------------------------------------------------------------------------

@router.get("/wallet")
def wallet(db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    return service.wallet_view(db, service.get_or_create_wallet(db, me.id))


@router.get("/transfers", response_model=list[TransferOut])
def transfers(db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    w = service.get_or_create_wallet(db, me.id)
    return db.query(BridgeTransfer).filter(BridgeTransfer.wallet_id == w.id).order_by(BridgeTransfer.created_at.desc()).all()


# --- payment mandates for agents (WP-013) --------------------------------------------

class MandateCreate(BaseModel):
    agent_id: str
    purposes: list[str] = Field(..., min_length=1, description="What this agent may pay for")
    currency: str = Field("USD", pattern="^[A-Z]{3}$")
    max_per_payment: float = Field(..., gt=0)
    max_total: float = Field(..., gt=0)
    payee_user_ids: list[str] | None = Field(default=None, description="Omit to allow any payee")
    requires_evidence: bool = True
    hours: float = Field(72, gt=0, le=8760, description="How long the mandate lasts")
    note: str | None = Field(default=None, max_length=2000)


class MandateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    agent_id: str
    granted_by_user_id: str
    purposes: list
    currency: str
    max_per_payment: float
    max_total: float
    spent_total: float
    payee_user_ids: list | None
    requires_evidence: bool
    expires_at: datetime
    status: str
    note: str | None
    revoked_reason: str | None


class AgentPaymentIn(BaseModel):
    mandate_id: str
    payee_user_id: str
    amount: float = Field(..., gt=0)
    currency: str = Field("USD", pattern="^[A-Z]{3}$")
    purpose: str = Field(..., min_length=1, max_length=200)
    evidence_ref: str | None = Field(default=None, max_length=500,
                                     description="What this payment answers to: an invoice, a delivery")
    rail: str | None = None


class AgentPaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    mandate_id: str | None
    agent_id: str
    payer_user_id: str
    payee_user_id: str | None
    amount: float
    currency: str
    purpose: str
    evidence_ref: str | None
    status: str
    refusal_reason: str | None
    rail: str | None
    settlement_ref: str | None
    transaction_object: dict | None


@router.post("/mandates", response_model=MandateOut, status_code=201)
def grant_mandate(payload: MandateCreate, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Authorise an agent to spend your money, within limits you set and can withdraw."""
    agent = db.get(Agent, payload.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="agent not found")
    if agent.status != "active":
        raise HTTPException(status_code=409, detail=f"that agent is {agent.status}")
    if db.get(User, agent.steward_user_id) is None:
        raise HTTPException(status_code=409, detail="that agent has no steward, so it has no write access")
    data = payload.model_dump(exclude={"hours"})
    m = PaymentMandate(granted_by_user_id=me.id, expires_at=utcnow() + timedelta(hours=payload.hours), **data)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@router.get("/mandates", response_model=list[MandateOut])
def list_mandates(db: Session = Depends(get_db), principal=Depends(require_any_role(ROLE_USER, ROLE_AGENT))):
    """Yours to answer for: mandates you granted, or — for an agent — the ones it holds."""
    if has_any_role(principal, ROLE_AGENT):
        agent = db.query(Agent).filter(Agent.did == principal["sub"]).first()
        if agent is None:
            raise HTTPException(status_code=403, detail="unknown agent")
        return db.query(PaymentMandate).filter(PaymentMandate.agent_id == agent.id).all()
    me = current_user_or_none(principal, db)
    if me is None:
        raise HTTPException(status_code=403, detail="no CAN profile for this identity")
    return db.query(PaymentMandate).filter(PaymentMandate.granted_by_user_id == me.id).all()


@router.post("/mandates/{mandate_id}/revoke", response_model=MandateOut)
def revoke_mandate(mandate_id: str, reason: str | None = None, db: Session = Depends(get_db),
                   me: User = Depends(get_current_user)):
    """Withdraw it. The next payment attempt is refused, whatever the agent thinks it may do."""
    m = db.get(PaymentMandate, mandate_id)
    if not m or m.granted_by_user_id != me.id:
        raise HTTPException(status_code=404, detail="mandate not found")
    m.status = "revoked"
    m.revoked_at = utcnow()
    m.revoked_reason = reason
    db.commit()
    db.refresh(m)
    return m


@router.post("/payments", response_model=AgentPaymentOut)
def agent_pay(payload: AgentPaymentIn, db: Session = Depends(get_db), agent: Agent = Depends(get_current_agent)):
    """An agent pays under a mandate. Outside it, nothing reaches a rail and the refusal is kept."""
    m = db.get(PaymentMandate, payload.mandate_id)
    if not m:
        raise HTTPException(status_code=404, detail="mandate not found")
    if not db.get(User, payload.payee_user_id):
        raise HTTPException(status_code=404, detail="payee not found")
    payment = pay(db, mandate=m, agent_id=agent.id, agent_did=agent.did,
                  steward_user_id=agent.steward_user_id, payee_user_id=payload.payee_user_id,
                  amount=payload.amount, currency=payload.currency, purpose=payload.purpose,
                  evidence_ref=payload.evidence_ref, rail_name=payload.rail)
    if payment.status == "refused":
        # 402: the payer's own rules refused it, not the server. The record is returned.
        raise HTTPException(status_code=402, detail={"refused": payment.refusal_reason,
                                                     "payment_id": payment.id,
                                                     "mandate_id": m.id})
    return payment


@router.get("/payments", response_model=list[AgentPaymentOut])
def list_agent_payments(status: str | None = Query(None, pattern="^(settled|refused)$"),
                        db: Session = Depends(get_db),
                        principal=Depends(require_any_role(ROLE_USER, ROLE_AGENT, ROLE_AUDITOR))):
    """What an agent did with your money, including what it tried and was refused."""
    q = db.query(AgentPayment)
    if has_any_role(principal, ROLE_AGENT):
        agent = db.query(Agent).filter(Agent.did == principal["sub"]).first()
        q = q.filter(AgentPayment.agent_id == (agent.id if agent else ""))
    elif not has_any_role(principal, ROLE_AUDITOR, ROLE_ADMIN):
        me = current_user_or_none(principal, db)
        mine = me.id if me else ""
        # The payer sees everything their agent tried. A payee sees only what actually
        # settled: a refusal is the payer's business, not the world's.
        q = q.filter((AgentPayment.payer_user_id == mine) |
                     ((AgentPayment.payee_user_id == mine) & (AgentPayment.status == "settled")))
    if status:
        q = q.filter(AgentPayment.status == status)
    return q.order_by(AgentPayment.created_at.desc()).limit(200).all()


# --- projects and contributions -----------------------------------------------------

@router.post("/projects", response_model=ProjectOut)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    p = Project(sponsor_user_id=me.id, **payload.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.get("/projects")
def list_projects(db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    sponsored = db.query(Project).filter(Project.sponsor_user_id == me.id).all()
    contributed_ids = {c.project_id for c in db.query(Contribution).filter(Contribution.contributor_user_id == me.id)}
    supplied_ids = {a.project_id for a in db.query(SupplierAgreement).filter(SupplierAgreement.supplier_user_id == me.id)}
    others = db.query(Project).filter(
        Project.id.in_(contributed_ids | supplied_ids), Project.sponsor_user_id != me.id
    ).all() if (contributed_ids | supplied_ids) else []
    dump = lambda rows: [ProjectOut.model_validate(r).model_dump(mode="json") for r in rows]  # noqa: E731
    return {"sponsored": dump(sponsored), "participating": dump(others)}


@router.get("/projects/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    p = _project(db, project_id)
    is_sponsor = p.sponsor_user_id == me.id
    q = db.query(Contribution).filter(Contribution.project_id == p.id)
    if not is_sponsor:
        q = q.filter(or_(Contribution.contributor_user_id == me.id, Contribution.status == "accepted"))
    agreements = db.query(SupplierAgreement).filter(SupplierAgreement.project_id == p.id)
    if not is_sponsor:
        agreements = agreements.filter(SupplierAgreement.supplier_user_id == me.id)
    return {
        "project": ProjectOut.model_validate(p).model_dump(mode="json"),
        "is_sponsor": is_sponsor,
        "funding_mix": service.funding_mix(db, p),
        "contributions": [ContributionOut.model_validate(c).model_dump(mode="json") for c in q.order_by(Contribution.created_at)],
        "supplier_agreements": [AgreementOut.model_validate(a).model_dump(mode="json") for a in agreements],
    }


@router.post("/projects/{project_id}/status", response_model=ProjectOut)
def set_status(project_id: str, payload: ProjectStatusIn, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    p = _project(db, project_id)
    _sponsor_only(p, me)
    p.status = payload.status
    db.commit()
    db.refresh(p)
    return p


@router.post("/projects/{project_id}/contributions", response_model=ContributionOut)
def contribute(project_id: str, payload: ContributionCreate, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Offer capital, in-kind value, pre-committed use or community contribution."""
    p = _project(db, project_id)
    return _wrap(service.propose_contribution, db, p, me.id, **payload.model_dump())


@router.post("/contributions/{contribution_id}/decision")
def decide(contribution_id: str, payload: ContributionDecisionIn, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """The sponsor accepts (issuing participation units and/or access rights) or rejects."""
    c = db.get(Contribution, contribution_id)
    if not c:
        raise HTTPException(status_code=404, detail="contribution not found")
    p = _project(db, c.project_id)
    _sponsor_only(p, me)
    result = _wrap(service.decide_contribution, db, c, p, decided_by=me.subject or me.id, **payload.model_dump())
    return {
        "contribution": ContributionOut.model_validate(result["contribution"]).model_dump(mode="json"),
        "issued": [{"id": h.id, "kind": h.kind, "amount": h.amount, "project_id": h.project_id} for h in result["issued"]],
        "reviews_required": result["reviews_required"],
        "funding_mix": service.funding_mix(db, p),
    }


# --- suppliers ----------------------------------------------------------------------

@router.post("/projects/{project_id}/suppliers", response_model=AgreementOut)
def add_supplier(project_id: str, payload: AgreementCreate, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Offer a supplier a split between cash now and a verified stake in what they help build."""
    p = _project(db, project_id)
    _sponsor_only(p, me)
    if not db.get(User, payload.supplier_user_id):
        raise HTTPException(status_code=404, detail="supplier user not found")
    a = SupplierAgreement(project_id=p.id, supplier_user_id=payload.supplier_user_id, scope=payload.scope,
                          cash_share=payload.cash_share, participation_share=round(1 - payload.cash_share, 6))
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@router.post("/agreements/{agreement_id}/response", response_model=AgreementOut)
def respond_to_agreement(agreement_id: str, payload: AgreementResponseIn, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Participation is always the supplier's choice, never a condition of being paid."""
    a = db.get(SupplierAgreement, agreement_id)
    if not a:
        raise HTTPException(status_code=404, detail="agreement not found")
    if a.supplier_user_id != me.id:
        raise HTTPException(status_code=403, detail="only the supplier can respond")
    a.accepted_by_supplier = "accepted" if payload.accept else "declined"
    if not payload.accept:
        a.cash_share, a.participation_share = 1.0, 0.0  # declining means all cash, paid faster
    db.commit()
    db.refresh(a)
    return a


@router.post("/agreements/{agreement_id}/invoices", response_model=InvoiceOut)
def submit_invoice(agreement_id: str, payload: InvoiceCreate, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    a = db.get(SupplierAgreement, agreement_id)
    if not a:
        raise HTTPException(status_code=404, detail="agreement not found")
    if a.supplier_user_id != me.id:
        raise HTTPException(status_code=403, detail="only the supplier can invoice")
    inv = SupplierInvoice(agreement_id=a.id, **payload.model_dump())
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


@router.get("/agreements/{agreement_id}/invoices", response_model=list[InvoiceOut])
def list_invoices(agreement_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    a = db.get(SupplierAgreement, agreement_id)
    if not a:
        raise HTTPException(status_code=404, detail="agreement not found")
    p = _project(db, a.project_id)
    if me.id not in {a.supplier_user_id, p.sponsor_user_id}:
        raise HTTPException(status_code=403, detail="not your invoices")
    return db.query(SupplierInvoice).filter(SupplierInvoice.agreement_id == a.id).order_by(SupplierInvoice.created_at).all()


@router.post("/invoices/{invoice_id}/verify", response_model=InvoiceOut)
def verify_invoice(invoice_id: str, payload: InvoiceVerifyIn, db: Session = Depends(get_db),
                   me: User = Depends(get_current_user), principal=Depends(get_current_principal)):
    """Certify delivery. Only verified work is paid."""
    inv = db.get(SupplierInvoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="invoice not found")
    a = db.get(SupplierAgreement, inv.agreement_id)
    p = _project(db, a.project_id)
    if p.sponsor_user_id != me.id and not has_any_role(principal, ROLE_REVIEWER, ROLE_ADMIN):
        raise HTTPException(status_code=403, detail="only the sponsor or a reviewer can verify delivery")
    if inv.status not in {"submitted", "verified"}:
        raise HTTPException(status_code=409, detail=f"invoice is {inv.status}")
    inv.status = "verified" if payload.approve else "rejected"
    inv.verified_by = principal["sub"]
    inv.verified_at = utcnow()
    if payload.delivery_evidence_ref:
        inv.delivery_evidence_ref = payload.delivery_evidence_ref
    db.commit()
    db.refresh(inv)
    return inv


@router.post("/invoices/{invoice_id}/pay")
def pay_invoice(invoice_id: str, rail: str | None = None, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    inv = db.get(SupplierInvoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="invoice not found")
    a = db.get(SupplierAgreement, inv.agreement_id)
    p = _project(db, a.project_id)
    _sponsor_only(p, me)
    result = _wrap(service.pay_invoice, db, inv, a, p, rail_name=rail, payer_subject=me.subject or me.id)
    return {
        "invoice": InvoiceOut.model_validate(result["invoice"]).model_dump(mode="json"),
        "cash_paid": result["cash_paid"],
        "stake_value": result["stake_value"],
        "credited": [{"id": h.id, "kind": h.kind, "amount": h.amount} for h in result["credited"]],
        "settlement": result["settlement"],
    }


# --- leverage -----------------------------------------------------------------------

@router.post("/holdings/{holding_id}/pledges", response_model=PledgeOut)
def pledge(holding_id: str, payload: PledgeCreate, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Pledge verified value for liquidity without selling it. Double pledging is refused."""
    h = _holding(db, holding_id, me)
    return _wrap(service.create_pledge, db, h, **payload.model_dump())


@router.get("/holdings/{holding_id}/pledges", response_model=list[PledgeOut])
def list_pledges(holding_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    h = _holding(db, holding_id, me)
    return db.query(Pledge).filter(Pledge.holding_id == h.id).order_by(Pledge.created_at).all()


@router.delete("/pledges/{pledge_id}", response_model=PledgeOut)
def release(pledge_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    p = db.get(Pledge, pledge_id)
    if not p:
        raise HTTPException(status_code=404, detail="pledge not found")
    _holding(db, p.holding_id, me)
    return _wrap(service.release_pledge, db, p)


@router.post("/holdings/{holding_id}/settle")
def settle(holding_id: str, payload: SettleIn, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Settle direct value down into money when the holder needs to spend."""
    h = _holding(db, holding_id, me)
    w = service.get_or_create_wallet(db, me.id)
    result = _wrap(service.settle_down, db, w, h, amount=payload.amount, rail_name=payload.rail,
                   payer_subject=me.subject or me.id)
    return {
        "transfer": TransferOut.model_validate(result["transfer"]).model_dump(mode="json"),
        "cash": result["cash"],
        "settlement": result["settlement"],
    }
