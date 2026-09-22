"""Evidence-based valuation and stress scenarios (WP-011 sections 1, 2 and 4).

Deterministic and reproducible: the same evidence and the same public YAML always
produce the same value, scenario values and explanation.
"""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from app.core.config import settings
from app.value.models import AssetEvidence


@dataclass(frozen=True)
class InputDef:
    key: str
    category: str
    required: bool
    weight: float
    label: str
    min: float | None = None
    max: float | None = None
    default: float | None = None


@dataclass  # not frozen: a deployment or a test may tighten a threshold at runtime
class ValueConfig:
    categories: tuple[str, ...]
    inputs: dict[str, InputDef]
    scenarios: dict[str, dict]
    default_mandate: dict
    maintenance: dict
    exchange: dict
    discovery: dict
    introductions: dict


@lru_cache
def load_value_config(config_dir: str | None = None) -> ValueConfig:
    path = Path(config_dir or settings.LEDGER_CONFIG_DIR) / "value_assurance.yaml"
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)["value_assurance"]
    categories = tuple(raw["categories"])
    inputs = {}
    for k, v in raw["inputs"].items():
        if v["category"] not in categories:
            raise ValueError(f"value_assurance input {k}: unknown category {v['category']}")
        inputs[k] = InputDef(
            key=k,
            category=v["category"],
            required=bool(v.get("required", False)),
            weight=float(v.get("weight", 0)),
            label=v.get("label", k),
            min=v.get("min"),
            max=v.get("max"),
            default=v.get("default"),
        )
    total = sum(i.weight for i in inputs.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"value_assurance input weights must sum to 1.0 (got {total})")
    for name, s in raw["scenarios"].items():
        for key, op in s["changes"].items():
            if key not in inputs or not set(op) <= {"mul", "add"}:
                raise ValueError(f"scenario {name}: invalid change for {key}")
    return ValueConfig(
        categories=categories,
        inputs=inputs,
        scenarios=raw["scenarios"],
        default_mandate=raw.get("default_mandate", {}),
        maintenance=raw.get("maintenance", {"stale_evidence_days": 180, "reassess_after_days": 30, "min_confidence": 0.6}),
        exchange=raw.get("exchange", {"trusted_nodes": {}}),
        discovery=raw.get("discovery", {"k_anonymity": 2, "epoch_days": 7, "max_queries_per_hour": 120}),
        introductions=raw.get("introductions", {"ttl_hours": 72, "max_message_chars": 500, "max_open_per_caller": 20}),
    )


def validate_input(key: str, value: float) -> None:
    d = load_value_config().inputs.get(key)
    if d is None:
        return
    if d.min is not None and value < d.min:
        raise ValueError(f"{key} must be >= {d.min}")
    if d.max is not None and value > d.max:
        raise ValueError(f"{key} must be <= {d.max}")


def current_evidence(db: Session, asset_id: str) -> list[AssetEvidence]:
    return (
        db.query(AssetEvidence)
        .filter(AssetEvidence.asset_id == asset_id, AssetEvidence.superseded_at.is_(None))
        .order_by(AssetEvidence.recorded_at)
        .all()
    )


def gather_inputs(evidence: list[AssetEvidence]) -> dict[str, dict]:
    """Current value and evidence status of every model input."""
    cfg = load_value_config()
    by_key = {e.key: e for e in evidence if e.key in cfg.inputs and e.value is not None}
    out = {}
    for key, d in cfg.inputs.items():
        e = by_key.get(key)
        if e is not None:
            status = "self_reported" if e.self_reported else "attested"
            out[key] = {"value": float(e.value), "status": status, "evidence_id": e.id,
                        "evidence_ref": e.evidence_ref, "category": d.category, "label": d.label}
        elif d.default is not None and not d.required:
            out[key] = {"value": float(d.default), "status": "default", "evidence_id": None,
                        "evidence_ref": None, "category": d.category, "label": d.label}
        else:
            out[key] = {"value": None, "status": "missing", "evidence_id": None,
                        "evidence_ref": None, "category": d.category, "label": d.label}
    return out


def confidence(inputs: dict[str, dict]) -> float:
    """Share of the model (by weight) backed by attested evidence."""
    cfg = load_value_config()
    return round(sum(cfg.inputs[k].weight for k, i in inputs.items() if i["status"] == "attested"), 6)


def value_from(v: dict[str, float]) -> dict:
    gross = v["units"] * v["occupancy"] * v["rent_per_unit_month"] * 12
    operating = gross * v["opex_ratio"]
    carbon_cost = v["carbon_tonnes_year"] * v["carbon_price"]
    noi = gross - operating - carbon_cost
    value = noi / v["cap_rate"] - v["capex_to_complete"]
    return {
        "gross_income": round(gross, 2),
        "operating_cost": round(operating, 2),
        "carbon_cost": round(carbon_cost, 2),
        "net_operating_income": round(noi, 2),
        "value": round(value, 2),
        "is_liability": value < 0,
    }


def apply_changes(values: dict[str, float], changes: dict) -> dict[str, float]:
    cfg = load_value_config()
    out = dict(values)
    for key, op in changes.items():
        x = out[key] * float(op.get("mul", 1.0)) + float(op.get("add", 0.0))
        d = cfg.inputs[key]
        if d.min is not None:
            x = max(x, d.min)
        if d.max is not None:
            x = min(x, d.max)
        out[key] = x
    return out


def valuate(inputs: dict[str, dict]) -> dict:
    """Base value, every stress scenario and a plain-language explanation."""
    cfg = load_value_config()
    missing = [k for k, i in inputs.items() if i["status"] == "missing"]
    conf = confidence(inputs)
    if missing:
        return {
            "complete": False,
            "missing_inputs": missing,
            "confidence": conf,
            "inputs": inputs,
            "explanation": [
                "The value cannot be calculated until these inputs have evidence: " + ", ".join(missing) + "."
            ],
        }

    values = {k: i["value"] for k, i in inputs.items()}
    base = value_from(values)
    scenarios = {}
    for name, s in cfg.scenarios.items():
        r = value_from(apply_changes(values, s["changes"]))
        change = r["value"] - base["value"]
        scenarios[name] = {
            "label": s["label"],
            **r,
            "change": round(change, 2),
            "change_pct": round(100 * change / abs(base["value"]), 2) if base["value"] else None,
        }

    explanation = [
        "Value = net operating income / cap rate - capital cost to complete.",
        f"Net operating income {base['net_operating_income']:,.0f} = gross {base['gross_income']:,.0f}"
        f" - operating {base['operating_cost']:,.0f} - carbon {base['carbon_cost']:,.0f}.",
        f"{round(conf * 100)}% of the model (by weight) rests on attested evidence; the rest is"
        " self-reported or default.",
    ]
    if base["is_liability"]:
        explanation.append("On current evidence this asset is a liability: it costs more to hold than it earns.")
    turned = [s["label"] for s in scenarios.values() if s["is_liability"] and not base["is_liability"]]
    if turned:
        explanation.append("Value turns into liability under: " + "; ".join(turned) + ".")
    worst = min(scenarios.values(), key=lambda s: s["value"])
    explanation.append(f"Worst case tested: {worst['label']} ({worst['change_pct']}% vs base).")

    return {
        "complete": True,
        "missing_inputs": [],
        "confidence": conf,
        "inputs": inputs,
        "base": base,
        "scenarios": scenarios,
        "explanation": explanation,
    }


def sensitivity(values: dict[str, float], new_values: dict[str, float]) -> dict[str, float]:
    """Value effect of each changed input on its own (one at a time), for interpretation."""
    base = value_from(values)["value"]
    effects = {}
    for k in new_values:
        if new_values[k] != values.get(k):
            trial = dict(values)
            trial[k] = new_values[k]
            effects[k] = round(value_from(trial)["value"] - base, 2)
    return effects
