"""Loads the ledger definitions in <repo>/ledgers so the YAML is the single source of truth."""
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from app.core.config import settings

LEDGER_TYPES = ("contribution", "reliability", "care")


@dataclass(frozen=True)
class LedgerDef:
    name: str
    metrics: tuple[str, ...]
    weights: dict[str, float]
    opt_in_required: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class ScoringDef:
    base_weights: dict[str, float]
    care_uplift: float
    self_reported_weight: float


@dataclass(frozen=True)
class LedgerConfig:
    ledgers: dict[str, LedgerDef]
    scoring: ScoringDef


def _read(dirpath: Path, name: str) -> dict:
    with open(dirpath / f"{name}.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _check_weights(label: str, weights: dict[str, float]) -> None:
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"{label} weights must sum to 1.0 (got {total})")


@lru_cache
def load_ledger_config(config_dir: str | None = None) -> LedgerConfig:
    d = Path(config_dir or settings.LEDGER_CONFIG_DIR)
    ledgers: dict[str, LedgerDef] = {}
    for name in LEDGER_TYPES:
        raw = _read(d, name)[name]
        metrics = tuple(raw.get("metrics") or raw.get("factors") or [])
        weights = {k: float(v) for k, v in (raw.get("weighting") or {}).items()}
        if set(weights) != set(metrics):
            raise ValueError(f"{name}: weighting keys must match metrics/factors")
        _check_weights(name, weights)
        opt_in = frozenset(raw.get("opt_in_required") or [])
        if not opt_in <= set(metrics):
            raise ValueError(f"{name}: opt_in_required lists unknown factors")
        ledgers[name] = LedgerDef(name=name, metrics=metrics, weights=weights, opt_in_required=opt_in)

    s = _read(d, "scoring")["scoring"]
    base = {k: float(v) for k, v in s["base_weights"].items()}
    if set(base) != {"contribution", "reliability"}:
        raise ValueError("scoring.base_weights must cover contribution and reliability")
    _check_weights("scoring.base_weights", base)
    scoring = ScoringDef(
        base_weights=base,
        care_uplift=float(s.get("care_uplift", 0.0)),
        self_reported_weight=float(s.get("self_reported_weight", 0.0)),
    )
    return LedgerConfig(ledgers=ledgers, scoring=scoring)
