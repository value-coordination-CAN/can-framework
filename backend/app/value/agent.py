"""The WP-011 agentic loop: detect -> interpret -> recalculate -> explain -> act.

The agent acts only within the holder's explicit mandate, and its actions are limited to
alerts and requests (for attestation or human review). It never moves, pledges or transfers
value. Every run is recorded and attributable.
"""
from sqlalchemy.orm import Session

from app.value.engine import current_evidence, gather_inputs, sensitivity, valuate
from app.value.models import Asset, AssuranceRun

ACTIONS = {"alert", "request_attestation", "request_review"}


def effective_mandate(asset: Asset, default: dict) -> dict:
    m = dict(default)
    m.update(asset.mandate or {})
    m["allowed_actions"] = [a for a in m.get("allowed_actions", []) if a in ACTIONS]
    return m


def run_assurance(db: Session, asset: Asset, triggered_by: str, default_mandate: dict) -> AssuranceRun:
    previous = (
        db.query(AssuranceRun)
        .filter(AssuranceRun.asset_id == asset.id)
        .order_by(AssuranceRun.created_at.desc())
        .first()
    )
    inputs = gather_inputs(current_evidence(db, asset.id))
    now_values = {k: i["value"] for k, i in inputs.items()}
    prev_values = (previous.inputs or {}) if previous else {}

    # 1. Detect: what changed since the last run?
    changes = []
    for k, v in now_values.items():
        before = prev_values.get(k)
        if before != v:
            changes.append({
                "input": k,
                "label": inputs[k]["label"],
                "before": before,
                "after": v,
                "status": inputs[k]["status"],
            })
    detect = {
        "first_run": previous is None,
        "changes": changes,
        "summary": "First assessment of this asset." if previous is None
        else (f"{len(changes)} input(s) changed since the last run." if changes else "No inputs changed since the last run."),
    }

    # 2. Interpret: what does each change mean for value on its own?
    interpret = {"effects": {}, "summary": "Nothing to interpret."}
    complete_prev = previous is not None and all(prev_values.get(k) is not None for k in now_values)
    complete_now = all(v is not None for v in now_values.values())
    if complete_prev and complete_now and changes:
        effects = sensitivity(prev_values, now_values)
        interpret = {
            "effects": effects,
            "summary": "; ".join(
                f"{inputs[k]['label']}: {'+' if d >= 0 else ''}{d:,.0f} on its own" for k, d in effects.items()
            ),
        }
    elif changes and not complete_now:
        interpret["summary"] = "Some required inputs are still missing, so effects cannot be isolated yet."

    # 3. Recalculate: base value and every stress scenario.
    valuation = valuate(inputs)
    base_value = valuation["base"]["value"] if valuation["complete"] else None

    # 4. Explain: in terms the holder and affected parties can read and contest.
    lines = list(valuation["explanation"])
    if previous is not None and previous.base_value is not None and base_value is not None:
        delta = base_value - previous.base_value
        pct = 100 * delta / abs(previous.base_value) if previous.base_value else 0.0
        lines.insert(0, f"Base value moved {'+' if delta >= 0 else ''}{delta:,.0f} ({pct:+.1f}%) since the last run.")
    explain = {"lines": lines}

    # 5. Act: only within the holder's mandate, and only alerts and requests.
    mandate = effective_mandate(asset, default_mandate)
    allowed = set(mandate["allowed_actions"])
    candidates = []
    if valuation["complete"]:
        if previous is not None and previous.base_value and base_value is not None:
            drop_pct = 100 * (previous.base_value - base_value) / abs(previous.base_value)
            if drop_pct > float(mandate.get("alert_drop_pct", 10)):
                candidates.append(("alert", f"Base value fell {drop_pct:.1f}%, above the {mandate.get('alert_drop_pct')}% threshold."))
        if mandate.get("flag_liability", True):
            if valuation["base"]["is_liability"]:
                candidates.append(("request_review", "The asset is a liability on current evidence."))
            else:
                turned = [s["label"] for s in valuation["scenarios"].values() if s["is_liability"]]
                if turned:
                    candidates.append(("alert", "Value turns into liability under: " + "; ".join(turned) + "."))
    else:
        candidates.append(("request_attestation", "Evidence needed for: " + ", ".join(valuation["missing_inputs"]) + "."))
    if valuation["confidence"] < float(mandate.get("min_confidence", 0.6)):
        weak = [inputs[k]["label"] for k, i in inputs.items() if i["status"] in {"self_reported", "missing"}]
        candidates.append((
            "request_attestation",
            f"Evidence confidence {valuation['confidence']:.0%} is below {float(mandate.get('min_confidence', 0.6)):.0%}."
            + (" Attest: " + ", ".join(weak) + "." if weak else ""),
        ))

    actions = []
    for kind, message in candidates:
        if mandate.get("enabled") and kind in allowed:
            actions.append({"type": kind, "message": message, "taken": True})
        else:
            actions.append({
                "type": kind,
                "message": message,
                "taken": False,
                "why_not": "no active mandate" if not mandate.get("enabled") else f"'{kind}' is not in the mandate",
            })

    run = AssuranceRun(
        asset_id=asset.id,
        triggered_by=triggered_by,
        inputs=now_values,
        base_value=base_value,
        confidence=valuation["confidence"],
        steps={
            "detect": detect,
            "interpret": interpret,
            "recalculate": valuation,
            "explain": explain,
            "act": {"mandate": mandate},
        },
        actions=actions,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run
