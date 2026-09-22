from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC timestamp, matching the existing DateTime (without time zone) columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
