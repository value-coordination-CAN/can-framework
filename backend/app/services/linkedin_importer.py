import csv
import hashlib
import hmac
import io
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import utcnow
from app.models.network_edge import NetworkEdge

POSSIBLE_PROFILE_HEADERS = ["profile url", "public profile url", "url"]
POSSIBLE_EMAIL_HEADERS = ["email address", "email"]


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _pick(row: Dict[str, str], headers: List[str]) -> str:
    for h in headers:
        for k, v in row.items():
            if _norm(k) == h:
                return (v or "").strip()
    return ""


def hash_external(value: str) -> str:
    """Keyed hash (HMAC-SHA256 with a server-side pepper) so ids cannot be reversed by guessing emails."""
    v = _norm(value)
    h = hmac.new(settings.EXTERNAL_ID_PEPPER.encode("utf-8"), v.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"li:{h}"


def import_linkedin_connections(
    db: Session,
    user_id: str,
    csv_bytes: bytes,
    replace: bool,
    source_filename: str | None = None,
) -> Dict[str, Any]:
    """Store one edge per connection. Connections' names and emails are not stored:
    they have not consented to CAN, so only a keyed hash of their profile URL or email is kept."""
    if replace:
        db.query(NetworkEdge).filter(
            NetworkEdge.source_user_id == user_id,
            NetworkEdge.source_system == "linkedin_export",
        ).delete(synchronize_session=False)

    text = csv_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    now = utcnow()

    imported = 0
    skipped = 0
    seen: set[str] = set()

    for row in reader:
        key = _pick(row, POSSIBLE_PROFILE_HEADERS) or _pick(row, POSSIBLE_EMAIL_HEADERS)
        if not key:
            skipped += 1
            continue
        external_id = hash_external(key)
        if external_id in seen:
            skipped += 1
            continue
        seen.add(external_id)

        db.add(NetworkEdge(
            source_user_id=user_id,
            target_user_id=None,
            target_external_id=external_id,
            edge_type="connected",
            weight=0.30,
            evidence_ref=f"linkedin_export:{now.date().isoformat()}",
            source_system="linkedin_export",
            created_at=now,
            display_name=None,
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
