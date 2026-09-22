"""Maintaining value: what needs looking at, and how one asset connects to everything else.

`work_items` is the queue an integrating AI system reads to know what to do next.
`asset_map` is how it finds its way around: an asset, its evidence, the project that built
it, and the people and suppliers who contributed.
"""
from datetime import timedelta

from sqlalchemy.orm import Session

from app.bridge.models import Contribution, Project, SupplierAgreement
from app.core.time import utcnow
from app.value.access import FULL, may_see_valuation
from app.value.engine import current_evidence, gather_inputs, load_value_config, valuate
from app.value.models import Asset, AssetShare, AssuranceRun, EvidenceProposal

# Each item says what is wrong, and what would fix it.
ITEM_TYPES = {
    "missing_evidence": "An input the model needs has no evidence at all",
    "stale_evidence": "Evidence is older than the maintenance threshold",
    "low_confidence": "Too little of the value rests on attested evidence",
    "liability_risk": "Value turns into liability under a tested scenario",
    "never_assessed": "No assurance run has been made for this asset",
    "assessment_due": "The last assurance run is older than the threshold",
    "open_proposal": "A proposed revaluation is waiting for the holder or an attester",
}


def _age_days(when) -> float:
    return (utcnow() - when).total_seconds() / 86400 if when else 1e9


def asset_work(db: Session, asset: Asset, access) -> list[dict]:
    cfg = load_value_config()
    m = cfg.maintenance
    items: list[dict] = []

    def add(kind: str, detail: str, action: str, **extra):
        items.append({"asset_id": asset.id, "asset_name": asset.name, "type": kind,
                      "detail": detail, "suggested_action": action, **extra})

    evidence = current_evidence(db, asset.id)
    inputs = gather_inputs(evidence)
    valuation = valuate(inputs) if may_see_valuation(access) else None

    for key, i in inputs.items():
        if i["status"] == "missing":
            add("missing_evidence", f"{i['label']} has no evidence", "Ask an attester to record it", input=key)
    cutoff = timedelta(days=float(m.get("stale_evidence_days", 180)))
    for e in evidence:
        if e.key in inputs and _age_days(e.recorded_at) > cutoff.days:
            add("stale_evidence", f"{e.key} was last recorded {int(_age_days(e.recorded_at))} days ago",
                "Refresh it, or propose a revaluation with a source", input=e.key)

    if valuation is not None and valuation["complete"]:
        if valuation["confidence"] < float(m.get("min_confidence", 0.6)):
            add("low_confidence", f"Only {valuation['confidence']:.0%} of the model rests on attested evidence",
                "Seek attestation rather than more derivation", confidence=valuation["confidence"])
        risky = [s["label"] for s in valuation["scenarios"].values() if s["is_liability"]]
        if risky:
            add("liability_risk", "Value turns into liability under: " + "; ".join(risky),
                "Tell the holder and record the reasoning", scenarios=len(risky))

    last_run = db.query(AssuranceRun).filter(AssuranceRun.asset_id == asset.id).order_by(
        AssuranceRun.created_at.desc()).first()
    if access == FULL:
        if last_run is None:
            add("never_assessed", "No assurance run has been made", "Run the assurance loop")
        elif _age_days(last_run.created_at) > float(m.get("reassess_after_days", 30)):
            add("assessment_due", f"Last assessed {int(_age_days(last_run.created_at))} days ago",
                "Run the assurance loop again")
        open_proposals = db.query(EvidenceProposal).filter(
            EvidenceProposal.asset_id == asset.id, EvidenceProposal.status == "open").count()
        if open_proposals:
            add("open_proposal", f"{open_proposals} proposed revaluation(s) waiting",
                "Accept or reject them; a proposal is not evidence", count=open_proposals)
    return items


def work_items(db: Session, visible: dict, limit: int = 200) -> list[dict]:
    out: list[dict] = []
    for asset_id, access in visible.items():
        asset = db.get(Asset, asset_id)
        if asset is None:
            continue
        out.extend(asset_work(db, asset, access))
        if len(out) >= limit:
            break
    return out[:limit]


def asset_map(db: Session, asset: Asset, access) -> dict:
    """How this asset connects: evidence, the project that built it, and who contributed."""
    evidence = current_evidence(db, asset.id)
    if access != FULL:
        evidence = [e for e in evidence if e.category in access]
    by_category: dict[str, dict] = {}
    for e in evidence:
        c = by_category.setdefault(e.category, {"count": 0, "attested": 0, "keys": []})
        c["count"] += 1
        c["attested"] += 0 if e.self_reported else 1
        c["keys"].append(e.key)

    projects = db.query(Project).filter(Project.asset_id == asset.id).all()
    project_nodes = []
    for p in projects:
        accepted = db.query(Contribution).filter(
            Contribution.project_id == p.id, Contribution.status == "accepted").all()
        project_nodes.append({
            "id": p.id, "name": p.name, "status": p.status, "currency": p.currency,
            "target_amount": p.target_amount,
            "contributions": {
                "accepted": len(accepted),
                "value": round(sum(c.accepted_value or 0 for c in accepted), 2),
                "by_source": {s: round(sum(c.accepted_value or 0 for c in accepted if c.source_type == s), 2)
                              for s in {c.source_type for c in accepted}},
                "contributors": len({c.contributor_user_id for c in accepted}),
            },
            "suppliers": db.query(SupplierAgreement).filter(SupplierAgreement.project_id == p.id).count(),
        })

    runs = db.query(AssuranceRun).filter(AssuranceRun.asset_id == asset.id).order_by(
        AssuranceRun.created_at.desc()).limit(5).all()
    return {
        "asset": {"id": asset.id, "name": asset.name, "kind": asset.kind, "currency": asset.currency,
                  "holder_user_id": asset.holder_user_id if access == FULL else None},
        "access": FULL if access == FULL else sorted(access),
        "evidence_by_category": by_category,
        "projects": project_nodes,
        "shares": db.query(AssetShare).filter(AssetShare.asset_id == asset.id).count() if access == FULL else None,
        "assurance": [{"id": r.id, "created_at": r.created_at, "base_value": r.base_value,
                       "confidence": r.confidence, "actions": len(r.actions or [])} for r in runs],
        "note": "Evidence, the project that built the value, and the contributions behind it, in one view.",
    }
