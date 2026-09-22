"""Commitments: being findable without publishing a catalogue (WP-012 §4).

A commitment is a hash over a few **coarse** attributes of a discoverable item, mixed with
an epoch salt that every node knows, so that a searcher who forms the same attributes
produces the same commitment and gets a match.

Being honest about what this does and does not do:

- it **answers** match / no match; there is no endpoint that lists commitments, so a node
  cannot be scraped for a catalogue of what it holds;
- the attribute space is small, so a determined caller could probe it. Enumeration is
  resisted by **rate limits** and by a **k-anonymity threshold**: a node answers only where
  at least `k` of its items share the commitment, so a match never points at one item;
- the epoch salt **rotates**, so commitments gathered in one period do not carry into the
  next;
- a match reveals that something matching exists on this node. It reveals nothing about
  what, whose, how much, or where precisely. That comes after an introduction, by consent.
"""
import hashlib
import hmac
import json
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import utcnow
from app.value.engine import load_value_config
from app.value.map_models import MapItem

# The coarse attributes a commitment is formed over. Deliberately few, deliberately blunt.
ATTRIBUTES = ("item_type", "item_class", "region", "period")


def discovery_rules() -> dict:
    d = dict(load_value_config().discovery or {})
    d.setdefault("k_anonymity", 2)
    d.setdefault("epoch_days", 7)
    d.setdefault("max_queries_per_hour", 120)
    return d


def current_epoch() -> str:
    """Rotates every `epoch_days`, so commitments do not carry across periods."""
    days = int(discovery_rules()["epoch_days"])
    return f"E{int(utcnow().timestamp() // (days * 86400))}"


def epoch_salt(epoch: str | None = None) -> str:
    """Public, shared and derived from the node network's epoch: every node can form it,
    so a searcher can build the same commitment as the holder."""
    return hashlib.sha256(f"can-map-epoch:{epoch or current_epoch()}".encode()).hexdigest()[:32]


def period_of(item: MapItem) -> str:
    """Availability rounded to a quarter: precise enough to be useful, blunt enough to hide."""
    d = item.available_from or item.created_at.date()
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def commitment(item_type: str, item_class: str, region: str, period: str, epoch: str | None = None) -> str:
    payload = json.dumps({"item_type": item_type, "item_class": item_class.lower().strip(),
                          "region": region.upper().strip(), "period": period}, sort_keys=True)
    return hmac.new(epoch_salt(epoch).encode(), payload.encode(), hashlib.sha256).hexdigest()


def commitment_for(item: MapItem, epoch: str | None = None) -> str:
    return commitment(item.item_type, item.item_class, item.region, period_of(item), epoch)


def matching_items(db: Session, target: str, epoch: str | None = None) -> list[MapItem]:
    items = db.query(MapItem).filter(MapItem.discoverable.is_(True), MapItem.status == "open").all()
    return [i for i in items if commitment_for(i, epoch) == target]


def answer_query(db: Session, target: str, epoch: str | None = None) -> dict:
    """Match or no match, under the k-anonymity threshold. Never contents, never identities."""
    rules = discovery_rules()
    k = int(rules["k_anonymity"])
    found = matching_items(db, target, epoch)
    match = len(found) >= k
    return {
        "commitment": target,
        "epoch": epoch or current_epoch(),
        "match": match,
        "node_id": settings.NODE_ID if match else None,
        "k_anonymity": k,
        "note": ("Something matching exists on this node. Ask for an introduction; the holder decides."
                 if match else
                 f"No answer: either nothing matches, or fewer than {k} items match and the node will not "
                 "answer for a single item."),
    }


def rate_key(subject: str) -> str:
    return f"{subject}:{utcnow().strftime('%Y%m%d%H')}"


_query_counts: dict[str, int] = {}


def check_rate(subject: str) -> None:
    """Simple in-process limit. A deployment behind more than one worker uses shared storage."""
    limit = int(discovery_rules()["max_queries_per_hour"])
    key = rate_key(subject)
    _query_counts[key] = _query_counts.get(key, 0) + 1
    # keep the dict from growing without bound
    if len(_query_counts) > 10_000:
        cutoff = (utcnow() - timedelta(hours=2)).strftime("%Y%m%d%H")
        for k in [k for k in _query_counts if k.rsplit(":", 1)[1] < cutoff]:
            _query_counts.pop(k, None)
    if _query_counts[key] > limit:
        raise PermissionError(f"discovery rate limit reached ({limit} queries an hour)")
