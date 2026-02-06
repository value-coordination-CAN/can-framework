import csv
import hashlib
import io
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models.network_edge import NetworkEdge

POSSIBLE_PROFILE_HEADERS = ["profile url", "public profile url", "url"]
POSSIBLE_EMAIL_HEADERS = ["email address", "email"]
POSSIBLE_FIRSTNAME_HEADERS = ["first name", "firstname"]
POSSIBLE_LASTNAME_HEADERS = ["last name", "lastname"]

def _norm(s: str) -> str:
    return (s or "").strip().lower()

def _pick(row: Dict[str, str], headers: List[str]) -> str:
    for h in headers:
        for k, v in row.items():
            if _norm(k) == h:
                return (v or "").strip()
    return ""

def _hash_external(value: str) -> str:
    v = value.strip()
    h = hashlib.sha256(v.encode("utf-8")).hexdigest()
    return f"li:{h}"

def import_linkedin_connections(
    db: Session,
    user_id: str,
    csv_bytes: bytes,
    replace: bool,
    source_filename: str | None = None,
) -> Dict[str, Any]:
    if replace:
        db.query(NetworkEdge).filter(
            NetworkEdge.source_user_id == user_id,
            NetworkEdge.source_system == "linkedin_export",
        ).delete()

    text = csv_bytes.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    now = datetime.now(timezone.utc)

    imported = 0
    skipped = 0

    for row in reader:
        profile = _pick(row, POSSIBLE_PROFILE_HEADERS)
        email = _pick(row, POSSIBLE_EMAIL_HEADERS)
        key = profile or email
        if not key:
            skipped += 1
            continue

        external_id = _hash_external(key)
        display_name = " ".join([_pick(row, POSSIBLE_FIRSTNAME_HEADERS), _pick(row, POSSIBLE_LASTNAME_HEADERS)]).strip()

        db.add(NetworkEdge(
            source_user_id=user_id,
            target_user_id=None,
            target_external_id=external_id,
            edge_type="connected",
            weight=0.30,
            evidence_ref=f"linkedin_export:{now.date().isoformat()}:{source_filename or ''}",
            source_system="linkedin_export",
            created_at=now,
            display_name=display_name or None,
        ))
        imported += 1

    db.commit()
    return {
        "source": "linkedin_export",
        "user_id": user_id,
        "imported": imported,
        "skipped": skipped,
        "timestamp": now.isoformat(),
    }
