"""Agent payments under a mandate, carrying a trusted transaction object (WP-013).

The demonstration this implements: **an agent pays within an explicit mandate, a payment
outside it is refused before it reaches a rail, and the audit trail shows who authorised
what.**

Every payment produces a signed transaction object carrying the parties, the mandate it was
made under, the purpose, the evidence it answers to and the settlement reference — so what
travelled with the money can be verified afterwards by anyone, rather than reconstructed.
"""
import uuid

from sqlalchemy.orm import Session

from app.bridge.mandate_models import AgentPayment, PaymentMandate
from app.bridge.models import Holding, Wallet
from app.bridge.rails import get_rail
from app.bridge.service import credit, get_or_create_wallet, pledged_amount
from app.core.config import settings
from app.core.time import utcnow


class PaymentRefused(PermissionError):
    """Refused before anything reached a rail. The reason is recorded and shown."""


def _available_cash(db: Session, wallet: Wallet, currency: str) -> float:
    total = 0.0
    for h in db.query(Holding).filter(Holding.wallet_id == wallet.id, Holding.kind == "cash",
                                      Holding.currency == currency):
        total += h.amount - pledged_amount(db, h.id)
    return round(total, 2)


def check_mandate(db: Session, mandate: PaymentMandate, *, agent_id: str, payee_user_id: str,
                  amount: float, currency: str, purpose: str, evidence_ref: str | None) -> None:
    """Every reason a payment can be refused, checked before any money moves."""
    if mandate.agent_id != agent_id:
        raise PaymentRefused("that mandate was granted to a different agent")
    if mandate.status != "active":
        raise PaymentRefused(f"the mandate is {mandate.status}")
    if mandate.expires_at < utcnow():
        raise PaymentRefused("the mandate has expired")
    if currency != mandate.currency:
        raise PaymentRefused(f"the mandate is in {mandate.currency}, not {currency}")
    if purpose not in (mandate.purposes or []):
        raise PaymentRefused(f"'{purpose}' is not a purpose this mandate allows: {mandate.purposes}")
    if mandate.payee_user_ids is not None and payee_user_id not in mandate.payee_user_ids:
        raise PaymentRefused("that payee is not on the mandate")
    if amount > mandate.max_per_payment:
        raise PaymentRefused(f"{amount} is above the per-payment limit of {mandate.max_per_payment}")
    if round(mandate.spent_total + amount, 6) > mandate.max_total:
        remaining = round(mandate.max_total - mandate.spent_total, 2)
        raise PaymentRefused(f"that would exceed the mandate's total of {mandate.max_total}; {remaining} remains")
    if mandate.requires_evidence and not evidence_ref:
        raise PaymentRefused("this mandate requires evidence: say what the payment answers to")


def build_transaction_object(*, payment: AgentPayment, mandate: PaymentMandate, agent_did: str,
                             steward_user_id: str, settlement: dict) -> dict:
    """What travels with the money (WP-013 §3), signed by this node."""
    from app.value.documents import TRANSACTION_PROFILE, _b64, _unb64, document_root
    from nacl.signing import SigningKey

    doc = {
        "header": {
            "profile": TRANSACTION_PROFILE,
            "document_id": uuid.uuid4().hex,
            "issued_at": utcnow().isoformat(),
            "node_id": settings.NODE_ID,
            "subject": {"payment_id": payment.id},
        },
        "items": [],
        "transaction": {
            "parties": {"payer": payment.payer_user_id, "payee": payment.payee_user_id,
                        "agent": agent_did, "agent_steward": steward_user_id},
            "mandate": {"id": mandate.id, "granted_by": mandate.granted_by_user_id,
                        "purposes": mandate.purposes, "max_per_payment": mandate.max_per_payment,
                        "max_total": mandate.max_total, "expires_at": mandate.expires_at.isoformat(),
                        "requires_evidence": mandate.requires_evidence},
            "purpose": payment.purpose,
            "amount": payment.amount, "currency": payment.currency,
            "evidence_ref": payment.evidence_ref,
            "settlement": settlement,
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


def pay(db: Session, *, mandate: PaymentMandate, agent_id: str, agent_did: str, steward_user_id: str,
        payee_user_id: str, amount: float, currency: str, purpose: str, evidence_ref: str | None,
        rail_name: str | None = None) -> AgentPayment:
    """Pay under a mandate. A refusal is recorded too, and nothing reaches a rail."""
    payer_wallet = get_or_create_wallet(db, mandate.granted_by_user_id)

    def refuse(reason: str) -> AgentPayment:
        rec = AgentPayment(mandate_id=mandate.id, agent_id=agent_id,
                           payer_user_id=mandate.granted_by_user_id, payee_user_id=payee_user_id,
                           amount=amount, currency=currency, purpose=purpose, evidence_ref=evidence_ref,
                           status="refused", refusal_reason=reason)
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return rec

    try:
        check_mandate(db, mandate, agent_id=agent_id, payee_user_id=payee_user_id, amount=amount,
                      currency=currency, purpose=purpose, evidence_ref=evidence_ref)
    except PaymentRefused as e:
        return refuse(str(e))

    available = _available_cash(db, payer_wallet, currency)
    if available < amount:
        return refuse(f"the payer holds {available} {currency} free of pledges, less than {amount}")

    # Only now does anything settle.
    rail = get_rail(rail_name)
    result = rail.settle(amount=amount, currency=currency, reference=f"mandate:{mandate.id}",
                         payer=mandate.granted_by_user_id, payee=payee_user_id)

    remaining = amount
    for h in db.query(Holding).filter(Holding.wallet_id == payer_wallet.id, Holding.kind == "cash",
                                      Holding.currency == currency).order_by(Holding.created_at):
        free = h.amount - pledged_amount(db, h.id)
        take = min(free, remaining)
        h.amount = round(h.amount - take, 2)
        remaining = round(remaining - take, 2)
        if remaining <= 0:
            break
    credit(db, get_or_create_wallet(db, payee_user_id), kind="cash", amount=amount, currency=currency,
           description=f"Paid by an agent under mandate for {purpose}", evidence_ref=evidence_ref)

    mandate.spent_total = round(mandate.spent_total + amount, 2)
    if mandate.spent_total >= mandate.max_total:
        mandate.status = "exhausted"

    payment = AgentPayment(mandate_id=mandate.id, agent_id=agent_id,
                           payer_user_id=mandate.granted_by_user_id, payee_user_id=payee_user_id,
                           amount=amount, currency=currency, purpose=purpose, evidence_ref=evidence_ref,
                           status="settled", rail=result.rail, settlement_ref=result.external_ref)
    db.add(payment)
    db.flush()
    payment.transaction_object = build_transaction_object(
        payment=payment, mandate=mandate, agent_did=agent_did, steward_user_id=steward_user_id,
        settlement={"rail": result.rail, "reference": result.external_ref, "status": result.status},
    )
    db.commit()
    db.refresh(payment)
    return payment
