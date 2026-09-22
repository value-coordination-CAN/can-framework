"""Bridge wallet operations (WP-010).

Money keeps its role: everything can settle down into it. What changes is that
contributions other than cash earn a recorded stake, and that stake can be pledged,
settled or held as future-proofed value.
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.bridge.models import (
    CASH_SOURCES,
    HOLDING_KINDS,
    LAYER_DIRECT,
    LAYER_FIAT,
    SETTLEABLE_KINDS,
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
from app.bridge.rails import compliance_review_required, get_rail
from app.core.time import utcnow


class BridgeError(ValueError):
    pass


class BridgeForbidden(PermissionError):
    pass


# --- wallet -------------------------------------------------------------------------

def get_or_create_wallet(db: Session, user_id: str) -> Wallet:
    w = db.query(Wallet).filter(Wallet.user_id == user_id).first()
    if w is None:
        w = Wallet(user_id=user_id)
        db.add(w)
        db.commit()
        db.refresh(w)
    return w


def credit(db: Session, wallet: Wallet, *, kind: str, amount: float, currency: str | None = None,
           project_id: str | None = None, description: str | None = None,
           terms: dict | None = None, evidence_ref: str | None = None) -> Holding:
    layer = HOLDING_KINDS.get(kind)
    if layer is None:
        raise BridgeError(f"unknown holding kind '{kind}'; allowed: {sorted(HOLDING_KINDS)}")
    if amount < 0:
        raise BridgeError("amount cannot be negative")
    # Fungible positions merge; rights and claims with their own terms stay separate.
    if kind in {"cash", "tokenised_deposit", "offline_value", "participation_unit"}:
        existing = db.query(Holding).filter(
            Holding.wallet_id == wallet.id, Holding.kind == kind,
            Holding.project_id.is_(project_id) if project_id is None else Holding.project_id == project_id,
            Holding.currency.is_(currency) if currency is None else Holding.currency == currency,
        ).first()
        if existing is not None:
            existing.amount += amount
            db.commit()
            db.refresh(existing)
            return existing
    h = Holding(wallet_id=wallet.id, layer=layer, kind=kind, amount=amount, currency=currency,
                project_id=project_id, description=description, terms=terms, evidence_ref=evidence_ref)
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


def pledged_amount(db: Session, holding_id: str) -> float:
    total = db.query(func.sum(Pledge.amount)).filter(
        Pledge.holding_id == holding_id, Pledge.status == "active"
    ).scalar()
    return float(total or 0.0)


def wallet_view(db: Session, wallet: Wallet) -> dict:
    holdings = db.query(Holding).filter(Holding.wallet_id == wallet.id).order_by(Holding.created_at).all()
    out = {"wallet_id": wallet.id, "layers": {}, "holdings": []}
    for h in holdings:
        p = pledged_amount(db, h.id)
        out["holdings"].append({
            "id": h.id, "layer": h.layer, "kind": h.kind, "amount": h.amount, "currency": h.currency,
            "project_id": h.project_id, "description": h.description, "terms": h.terms,
            "evidence_ref": h.evidence_ref, "pledged": p, "free": round(h.amount - p, 6),
        })
        out["layers"].setdefault(h.layer, {"count": 0, "by_kind": {}})
        out["layers"][h.layer]["count"] += 1
        out["layers"][h.layer]["by_kind"][h.kind] = round(out["layers"][h.layer]["by_kind"].get(h.kind, 0) + h.amount, 6)
    return out


# --- project funding (WP-010 §3) ----------------------------------------------------

def funding_mix(db: Session, project: Project) -> dict:
    rows = db.query(Contribution).filter(
        Contribution.project_id == project.id, Contribution.status == "accepted"
    ).all()
    by_source = {s: 0.0 for s in SOURCE_TYPES}
    for c in rows:
        by_source[c.source_type] += float(c.accepted_value or 0.0)
    total = sum(by_source.values())
    cash = sum(v for s, v in by_source.items() if s in CASH_SOURCES)
    non_cash = total - cash
    return {
        "target_amount": project.target_amount,
        "currency": project.currency,
        "raised": round(total, 2),
        "still_needed": round(max(project.target_amount - total, 0), 2),
        "cash": round(cash, 2),
        "non_cash": round(non_cash, 2),
        "cash_share_pct": round(100 * cash / total, 2) if total else None,
        "cash_not_needed_pct": round(100 * non_cash / total, 2) if total else None,
        "by_source": {s: {"value": round(v, 2), "pct": round(100 * v / total, 2) if total else 0.0}
                      for s, v in by_source.items()},
        "contributors": len({c.contributor_user_id for c in rows}),
        "note": "Every unit of value contributed in kind is a unit that does not have to be raised in money.",
    }


def propose_contribution(db: Session, project: Project, user_id: str, *, source_type: str, description: str,
                         offered_value: float, wants: str, access_terms: dict | None) -> Contribution:
    if source_type not in SOURCE_TYPES:
        raise BridgeError(f"source_type must be one of {list(SOURCE_TYPES)}")
    if project.status not in {"funding", "delivering"}:
        raise BridgeError(f"project is {project.status}; contributions are not open")
    c = Contribution(project_id=project.id, contributor_user_id=user_id, source_type=source_type,
                     description=description, offered_value=offered_value, wants=wants, access_terms=access_terms)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def decide_contribution(db: Session, contribution: Contribution, project: Project, *, accept: bool,
                        accepted_value: float | None, valuation_basis: str | None, note: str | None,
                        decided_by: str) -> dict:
    """Accepting issues participation units, access rights, or both, into the contributor's wallet."""
    if contribution.status != "proposed":
        raise BridgeError(f"contribution already {contribution.status}")
    contribution.decided_by = decided_by
    contribution.decided_at = utcnow()
    contribution.decision_note = note
    issued = []
    if not accept:
        contribution.status = "rejected"
        db.commit()
        db.refresh(contribution)
        return {"contribution": contribution, "issued": issued, "reviews_required": []}

    value = float(accepted_value if accepted_value is not None else contribution.offered_value)
    if value <= 0:
        raise BridgeError("accepted value must be above zero")
    contribution.status = "accepted"
    contribution.accepted_value = value
    contribution.valuation_basis = valuation_basis

    wallet = get_or_create_wallet(db, contribution.contributor_user_id)
    if contribution.wants in {"participation", "both"}:
        units = round(value / project.unit_value, 6)
        issued.append(credit(db, wallet, kind="participation_unit", amount=units, project_id=project.id,
                             description=f"Participation in {project.name}",
                             terms={"unit_value": project.unit_value, "currency": project.currency,
                                    "source_type": contribution.source_type},
                             evidence_ref=valuation_basis))
    if contribution.wants in {"access", "both"}:
        issued.append(credit(db, wallet, kind="access_right", amount=1, project_id=project.id,
                             description=f"Access right in {project.name}",
                             terms=contribution.access_terms or {"note": "terms to be agreed"},
                             evidence_ref=valuation_basis))
    db.commit()
    db.refresh(contribution)
    return {
        "contribution": contribution,
        "issued": issued,
        "reviews_required": compliance_review_required(contribution.source_type, value),
    }


# --- suppliers (WP-010 §4) ----------------------------------------------------------

def pay_invoice(db: Session, invoice: SupplierInvoice, agreement: SupplierAgreement, project: Project,
                *, rail_name: str | None, payer_subject: str) -> dict:
    """Payment with proof: pay only what has been verified, splitting cash and participation."""
    if invoice.status != "verified":
        raise BridgeError("only verified invoices can be paid")
    cash = round(invoice.amount * agreement.cash_share, 2)
    stake_value = round(invoice.amount - cash, 2)
    wallet = get_or_create_wallet(db, agreement.supplier_user_id)

    rail = get_rail(rail_name)
    result = rail.settle(amount=cash, currency=project.currency, reference=f"invoice:{invoice.id}",
                         payer=payer_subject, payee=agreement.supplier_user_id)
    credited = []
    if cash > 0:
        credited.append(credit(db, wallet, kind="cash", amount=cash, currency=project.currency,
                               description=f"Invoice payment, {project.name}", evidence_ref=invoice.delivery_evidence_ref))
        db.add(BridgeTransfer(wallet_id=wallet.id, direction="settle_down", from_layer=LAYER_DIRECT,
                              to_layer=LAYER_FIAT, amount=cash, currency=project.currency,
                              rail=result.rail, external_ref=result.external_ref, status=result.status))
    if stake_value > 0:
        units = round(stake_value / project.unit_value, 6)
        credited.append(credit(db, wallet, kind="participation_unit", amount=units, project_id=project.id,
                               description=f"Future-proofed profit, {project.name}",
                               terms={"unit_value": project.unit_value, "currency": project.currency,
                                      "source": "supplier margin"},
                               evidence_ref=invoice.delivery_evidence_ref))
    invoice.status = "paid"
    invoice.paid_at = utcnow()
    invoice.settlement_ref = result.external_ref
    db.commit()
    return {"invoice": invoice, "cash_paid": cash, "stake_value": stake_value,
            "credited": credited, "settlement": result.__dict__}


# --- leverage: pledge and settle (WP-010 §2) ----------------------------------------

def create_pledge(db: Session, holding: Holding, *, amount: float, lender_user_id: str | None, note: str | None) -> Pledge:
    if holding.layer != LAYER_DIRECT:
        raise BridgeError("only direct-value holdings are pledged; money is simply spent")
    free = holding.amount - pledged_amount(db, holding.id)
    if amount <= 0:
        raise BridgeError("pledge amount must be above zero")
    if amount > free + 1e-9:
        raise BridgeError(f"cannot pledge {amount}: only {round(free, 6)} is unpledged (double pledging is visible)")
    p = Pledge(holding_id=holding.id, lender_user_id=lender_user_id, amount=amount, note=note)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def release_pledge(db: Session, pledge: Pledge) -> Pledge:
    if pledge.status != "active":
        raise BridgeError("pledge already released")
    pledge.status = "released"
    pledge.released_at = utcnow()
    db.commit()
    db.refresh(pledge)
    return pledge


def settle_down(db: Session, wallet: Wallet, holding: Holding, *, amount: float, rail_name: str | None,
                payer_subject: str) -> dict:
    """Settle a direct-value claim into money. Pledged value cannot be settled away."""
    if holding.layer != LAYER_DIRECT:
        raise BridgeError("this holding is already money")
    if holding.kind not in SETTLEABLE_KINDS:
        raise BridgeError(f"a {holding.kind.replace('_', ' ')} is a right to use something, not a claim for cash; "
                          f"only {', '.join(SETTLEABLE_KINDS)} settle into money")
    free = holding.amount - pledged_amount(db, holding.id)
    if amount <= 0 or amount > free + 1e-9:
        raise BridgeError(f"cannot settle {amount}: {round(free, 6)} is free of pledges")
    unit_value = float((holding.terms or {}).get("unit_value", 1.0))
    currency = (holding.terms or {}).get("currency") or holding.currency or "USD"
    cash = round(amount * unit_value, 2)

    rail = get_rail(rail_name)
    result = rail.settle(amount=cash, currency=currency, reference=f"holding:{holding.id}",
                         payer="project", payee=payer_subject)
    holding.amount = round(holding.amount - amount, 6)
    credit(db, wallet, kind="cash", amount=cash, currency=currency,
           description=f"Settled from {holding.kind}", evidence_ref=holding.evidence_ref)
    t = BridgeTransfer(wallet_id=wallet.id, direction="settle_down", from_layer=LAYER_DIRECT, to_layer=LAYER_FIAT,
                       holding_id=holding.id, amount=cash, currency=currency, rail=result.rail,
                       external_ref=result.external_ref, status=result.status)
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"transfer": t, "cash": cash, "settlement": result.__dict__}
