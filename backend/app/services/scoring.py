"""Explainable priority scoring.

- Each metric's score is the mean of its counted entries (values are normalised 0..1).
- A ledger's score is the YAML-weighted sum over all its metrics; a metric with no entries counts as 0.
- Self-reported entries are weighted by scoring.self_reported_weight (0 by default).
- Care is an uplift that can only raise priority, and only consented factors count.
- Every result carries an explanation the person can read and contest.
"""
from collections import defaultdict

from sqlalchemy.orm import Session

from app.db.models import LedgerEntry, ScoreSnapshot
from app.services.care_consent import active_consented_factors
from app.services.ledger_config import load_ledger_config


def _ledger_breakdown(entries, ledger_def, self_weight: float, allowed_metrics=None) -> dict:
    sums: dict[str, float] = defaultdict(float)
    weights_n: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    excluded_self = 0
    excluded_no_consent = 0

    for e in entries:
        if e.metric not in ledger_def.weights:
            continue
        if allowed_metrics is not None and e.metric not in allowed_metrics:
            excluded_no_consent += 1
            continue
        w = self_weight if e.self_reported else 1.0
        if w <= 0:
            excluded_self += 1
            continue
        sums[e.metric] += w * min(max(float(e.value), 0.0), 1.0)
        weights_n[e.metric] += w
        counts[e.metric] += 1

    metrics = {}
    score = 0.0
    for m, weight in ledger_def.weights.items():
        mean = sums[m] / weights_n[m] if weights_n[m] else 0.0
        contribution = weight * mean
        score += contribution
        metrics[m] = {
            "weight": weight,
            "mean": round(mean, 6),
            "entries_counted": counts[m],
            "contribution": round(contribution, 6),
        }
    return {
        "score": round(score, 6),
        "metrics": metrics,
        "excluded_self_reported": excluded_self,
        "excluded_without_consent": excluded_no_consent,
    }


def compute_score(db: Session, user_id: str) -> dict:
    cfg = load_ledger_config()
    entries_by_ledger = defaultdict(list)
    for e in db.query(LedgerEntry).filter(LedgerEntry.user_id == user_id).all():
        entries_by_ledger[e.ledger_type].append(e)

    self_w = cfg.scoring.self_reported_weight
    contribution = _ledger_breakdown(entries_by_ledger["contribution"], cfg.ledgers["contribution"], self_w)
    reliability = _ledger_breakdown(entries_by_ledger["reliability"], cfg.ledgers["reliability"], self_w)

    care_def = cfg.ledgers["care"]
    consented = active_consented_factors(db, user_id)
    allowed_care = (set(care_def.metrics) - care_def.opt_in_required) | (consented & care_def.opt_in_required)
    care = _ledger_breakdown(entries_by_ledger["care"], care_def, self_w, allowed_metrics=allowed_care)

    bw = cfg.scoring.base_weights
    base = bw["contribution"] * contribution["score"] + bw["reliability"] * reliability["score"]
    uplift = cfg.scoring.care_uplift * care["score"]
    overall = round(base + uplift, 6)

    explanation = {
        "formula": (
            f"{bw['contribution']} x contribution + {bw['reliability']} x reliability"
            f" + {cfg.scoring.care_uplift} x care (care can only raise priority)"
        ),
        "contribution": contribution,
        "reliability": reliability,
        "care": {**care, "consented_factors": sorted(consented & care_def.opt_in_required)},
        "base": round(base, 6),
        "care_uplift": round(uplift, 6),
        "overall": overall,
        "self_reported_weight": self_w,
        "notes": [
            "Only attested entries count unless self_reported_weight is above 0.",
            "Sensitive care factors count only with your explicit consent, which you can revoke.",
            "You can appeal any allocation decision based on this score.",
        ],
    }
    return {
        "contribution_score": contribution["score"],
        "reliability_score": reliability["score"],
        "care_score": care["score"],
        "overall_score": overall,
        "explanation": explanation,
    }


def calculate_and_store(db: Session, user_id: str) -> ScoreSnapshot:
    result = compute_score(db, user_id)
    snap = ScoreSnapshot(user_id=user_id, **result)
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap
