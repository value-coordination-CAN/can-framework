"""Portable value documents: how a node stores and exchanges what it knows about an asset.

A CAN node runs locally and holds its own records. A document is the unit it hands to
another node, or to a system that wants to check the value for itself:

- **self-describing**: the profile, the model and the statement travel with the figures;
- **verifiable**: every item is hashed with its own salt, and the document root covers them;
- **redactable**: an item can be withheld and the document still verifies, because the
  withheld item's hash remains. That is how a holder discloses revenue but not tenants;
- **signable**: a node signs the root with its own Ed25519 key, so the receiver knows which
  node stands behind it. Unsigned documents are accepted and marked as such.

The profile here is `can.value.v1`. A deployment may carry other profiles in the same
envelope; `profile` is what tells a receiver how to read `items`.
"""
import base64
import hashlib
import json
import secrets
from datetime import datetime

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import utcnow
from app.value.access import FULL
from app.value.engine import current_evidence, gather_inputs, load_value_config, valuate
from app.value.models import Asset, AssetEvidence

PROFILE = "can.value.v1"
MAP_PROFILE = "can.map.v1"
PROFILES = (PROFILE, MAP_PROFILE)


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()


def _sha(obj) -> str:
    return hashlib.sha256(_canon(obj)).hexdigest()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def node_identity() -> dict:
    """This node's identity. Without a signing key it can still exchange documents; they are
    simply unsigned, and a receiver treats them as hearsay."""
    key = settings.NODE_SIGNING_KEY
    if not key:
        return {"node_id": settings.NODE_ID, "public_key": None, "signing": "unsigned",
                "profiles": [PROFILE],
                "note": "Set NODE_SIGNING_KEY (32-byte seed, base64url) to sign documents."}
    sk = SigningKey(_unb64(key))
    return {"node_id": settings.NODE_ID, "public_key": _b64(bytes(sk.verify_key)),
            "signing": "ed25519", "profiles": [PROFILE]}


def build_document(db: Session, asset: Asset, access, *, disclose: set[str] | None = None,
                   include_valuation: bool = True) -> dict:
    """Build a document for this asset. `disclose` limits which evidence categories are
    revealed; withheld items keep their hash, so the document still verifies."""
    evidence = current_evidence(db, asset.id)
    if access != FULL:
        evidence = [e for e in evidence if e.category in access]

    items = []
    for e in evidence:
        salt = secrets.token_hex(8)
        content = {
            "category": e.category, "key": e.key, "value": e.value, "unit": e.unit,
            "text": e.text, "evidence_ref": e.evidence_ref,
            # ISO strings, not objects: a hash must survive the trip through JSON unchanged
            "recorded_at": e.recorded_at.isoformat() if e.recorded_at else None,
            "attested": not e.self_reported,
            "attester": e.attester_subject if not e.self_reported else None,
        }
        item = {"id": e.id, "salt": salt, "hash": _sha({"salt": salt, **content})}
        if disclose is None or e.category in disclose:
            item |= content
        else:
            item["withheld"] = True
        items.append(item)

    header = {
        "profile": PROFILE,
        "document_id": secrets.token_hex(16),
        "issued_at": utcnow().isoformat(),
        "node_id": settings.NODE_ID,
        "subject": {"asset_id": asset.id, "name": asset.name, "kind": asset.kind, "currency": asset.currency},
        "model": "income:can-value-engine-0.1",
        "disclosed_categories": sorted(disclose) if disclose else "all",
    }
    doc = {"header": header, "items": items}

    if include_valuation and (access == FULL or "valuation" in access):
        v = valuate(gather_inputs(current_evidence(db, asset.id)))
        section = {"complete": v["complete"], "confidence": v["confidence"],
                   "statement": " ".join(v["explanation"])}
        if v["complete"]:
            section |= {"value": v["base"]["value"], "is_liability": v["base"]["is_liability"],
                        "scenarios": {k: {"label": s["label"], "value": s["value"], "is_liability": s["is_liability"]}
                                      for k, s in v["scenarios"].items()}}
        doc["valuation"] = section

    doc["root"] = document_root(doc)
    key = settings.NODE_SIGNING_KEY
    if key:
        sk = SigningKey(_unb64(key))
        doc["signature"] = {"alg": "ed25519", "node_id": settings.NODE_ID,
                            "public_key": _b64(bytes(sk.verify_key)),
                            "value": _b64(sk.sign(doc["root"].encode()).signature)}
    return doc


def _hashed_item(item_id: str, content: dict, *, disclose: bool) -> dict:
    """One item of a document: content plus a salted hash, or the hash alone if withheld."""
    salt = secrets.token_hex(8)
    item = {"id": item_id, "salt": salt, "hash": _sha({"salt": salt, **content})}
    return item | content if disclose else item | {"withheld": True}


def build_map_slice(db: Session, holder_user_id: str, items, assets, *,
                    include: set[str] | None = None, purpose: str | None = None) -> dict:
    """A slice of this node's value map (WP-012 §3): the needs, capacities and assets the
    holder chooses to share, hashed item by item so redaction still verifies."""
    from app.value.engine import current_evidence, gather_inputs  # local import: avoids a cycle

    doc_items = []
    for it in items:
        content = {
            "record": "map_item", "item_type": it.item_type, "item_class": it.item_class,
            "title": it.title, "description": it.description, "quantity": it.quantity, "unit": it.unit,
            "region": it.region,
            "available_from": it.available_from.isoformat() if it.available_from else None,
            "available_until": it.available_until.isoformat() if it.available_until else None,
            "asset_id": it.asset_id, "attributes": it.attributes, "status": it.status,
        }
        doc_items.append(_hashed_item(it.id, content, disclose=include is None or it.item_type in include))

    for a in assets:
        inputs = gather_inputs(current_evidence(db, a.id))
        content = {
            "record": "asset", "name": a.name, "kind": a.kind, "currency": a.currency,
            "evidence_categories": sorted({i["category"] for i in inputs.values() if i["status"] != "missing"}),
            "attested_inputs": sorted(k for k, i in inputs.items() if i["status"] == "attested"),
        }
        doc_items.append(_hashed_item(a.id, content, disclose=include is None or "asset" in include))

    doc = {
        "header": {
            "profile": MAP_PROFILE,
            "document_id": secrets.token_hex(16),
            "issued_at": utcnow().isoformat(),
            "node_id": settings.NODE_ID,
            "subject": {"map_of": holder_user_id, "items": len(items), "assets": len(assets)},
            "purpose": purpose,
            "disclosed": sorted(include) if include else "all",
        },
        "items": doc_items,
    }
    doc["root"] = document_root(doc)
    key = settings.NODE_SIGNING_KEY
    if key:
        sk = SigningKey(_unb64(key))
        doc["signature"] = {"alg": "ed25519", "node_id": settings.NODE_ID,
                            "public_key": _b64(bytes(sk.verify_key)),
                            "value": _b64(sk.sign(doc["root"].encode()).signature)}
    return doc


def document_root(doc: dict) -> str:
    """Covers the header, every item hash (disclosed or withheld) and the valuation."""
    return _sha({
        "header": doc["header"],
        "items": sorted(i["hash"] for i in doc["items"]),
        "valuation": doc.get("valuation"),
    })


def verify_document(doc: dict, trusted_nodes: dict[str, str] | None = None) -> dict:
    """Check a document without trusting whoever handed it over."""
    problems: list[str] = []
    if doc.get("header", {}).get("profile") not in PROFILES:
        problems.append(f"unknown profile {doc.get('header', {}).get('profile')!r}")

    disclosed, withheld, bad_items = 0, 0, []
    for item in doc.get("items", []):
        if item.get("withheld"):
            withheld += 1
            continue
        disclosed += 1
        content = {k: v for k, v in item.items() if k not in {"id", "salt", "hash", "withheld"}}
        if _sha({"salt": item.get("salt"), **content}) != item.get("hash"):
            bad_items.append(item.get("id"))
    if bad_items:
        problems.append(f"{len(bad_items)} item(s) do not match their hash: {bad_items[:5]}")

    root_ok = document_root(doc) == doc.get("root")
    if not root_ok:
        problems.append("document root does not cover these items")

    sig = doc.get("signature")
    signature_ok, signer, trusted = None, None, False
    if sig:
        signer = sig.get("node_id")
        try:
            VerifyKey(_unb64(sig["public_key"])).verify(doc["root"].encode(), _unb64(sig["value"]))
            signature_ok = True
        except (BadSignatureError, KeyError, ValueError):
            signature_ok = False
            problems.append("signature does not verify")
        if signature_ok and trusted_nodes:
            trusted = trusted_nodes.get(signer) == sig.get("public_key")

    return {
        "profile": doc.get("header", {}).get("profile"),
        "valid": not problems,
        "root_matches": root_ok,
        "items": {"disclosed": disclosed, "withheld": withheld},
        "signed": bool(sig),
        "signature_valid": signature_ok,
        "signer_node": signer,
        "signer_trusted": trusted,
        "problems": problems,
        "note": "Withheld items keep their hash, so a redacted document still verifies. "
                "An unsigned document proves its own consistency, not who stands behind it.",
    }


def import_document(db: Session, doc: dict, holder_user_id: str, verification: dict) -> dict:
    """Take a document from another node into this one, as a new asset.

    Evidence arrives **attested only if the signing node is trusted**; otherwise it is held
    as unverified, because another node's word is not this node's evidence.
    """
    subject = doc["header"]["subject"]
    asset = Asset(holder_user_id=holder_user_id, name=subject.get("name", "Imported asset"),
                  kind=subject.get("kind", "imported"), currency=subject.get("currency", "USD"),
                  description=f"Imported from node {doc['header'].get('node_id')} "
                              f"(document {doc['header'].get('document_id')})")
    db.add(asset)
    db.flush()

    trusted = bool(verification.get("signer_trusted"))
    now = utcnow()
    imported, skipped = 0, 0
    for item in doc.get("items", []):
        if item.get("withheld") or item.get("value") is None and not item.get("text"):
            skipped += 1
            continue
        db.add(AssetEvidence(
            asset_id=asset.id, category=item["category"], key=item["key"], value=item.get("value"),
            text=item.get("text"), unit=item.get("unit"),
            evidence_ref=f"node:{doc['header'].get('node_id')}/doc:{doc['header'].get('document_id')}"
                         f"/item:{item['id']}",
            attester_subject=f"node:{doc['header'].get('node_id')}" if trusted else None,
            self_reported=not trusted, recorded_at=now,
        ))
        imported += 1
    db.commit()
    db.refresh(asset)
    return {
        "asset_id": asset.id,
        "imported_items": imported,
        "skipped_items": skipped,
        "treated_as": "attested" if trusted else "unverified",
        "source_node": doc["header"].get("node_id"),
        "document_id": doc["header"].get("document_id"),
        "note": "Evidence from an untrusted node is held as unverified: it does not raise "
                "confidence until someone here attests to it.",
    }


def trusted_nodes() -> dict[str, str]:
    """node_id -> public key, from the `exchange` section of ledgers/value_assurance.yaml."""
    return dict(load_value_config().exchange.get("trusted_nodes") or {})


def parse_issued_at(doc: dict) -> datetime | None:
    raw = doc.get("header", {}).get("issued_at")
    try:
        return datetime.fromisoformat(raw) if isinstance(raw, str) else raw
    except ValueError:
        return None
