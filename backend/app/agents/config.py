"""Loads ledgers/agents.yaml: what agents may record, their scopes and their limits."""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from app.core.config import settings


@dataclass(frozen=True)
class AgentRules:
    record_kinds: dict[str, str]
    scopes: dict[str, str]
    max_unreviewed_records: int
    max_records_per_hour: int
    max_input_bytes: int
    holdings: dict
    on_mismatch: str

    # Which scope allows which record kinds
    KIND_SCOPES = {
        "valuation": {"value.derive"},
        "check": {"value.derive", "score.derive", "general.derive"},
        "score": {"score.derive"},
        "summary": {"general.derive"},
        "recommendation": {"general.derive", "value.derive", "score.derive"},
        "recompute": {"value.derive", "score.derive", "general.derive"},
    }

    def scopes_for_kind(self, kind: str) -> set[str]:
        return self.KIND_SCOPES.get(kind, set())


@lru_cache
def load_agent_rules(config_dir: str | None = None) -> AgentRules:
    path = Path(config_dir or settings.LEDGER_CONFIG_DIR) / "agents.yaml"
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)["agents"]
    limits = raw["limits"]
    rules = AgentRules(
        record_kinds=raw["record_kinds"],
        scopes=raw["scopes"],
        max_unreviewed_records=int(limits["max_unreviewed_records"]),
        max_records_per_hour=int(limits["max_records_per_hour"]),
        max_input_bytes=int(limits["max_input_bytes"]),
        holdings=raw["holdings"],
        on_mismatch=raw["recomputation"]["on_mismatch"],
    )
    unknown = {k for kind in rules.record_kinds for k in rules.scopes_for_kind(kind)} - set(rules.scopes)
    if unknown:
        raise ValueError(f"agents.yaml: record kinds map to unknown scopes {sorted(unknown)}")
    if rules.holdings.get("may_hold_entitlement") or rules.holdings.get("may_hold_participation"):
        raise ValueError("agents.yaml: agents must not hold entitlements or participation")
    return rules
