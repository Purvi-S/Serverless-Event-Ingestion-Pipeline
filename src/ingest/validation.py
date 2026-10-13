"""Schema validation and normalization for incoming application events."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

ALLOWED_EVENT_TYPES = {"page_view", "click", "signup", "purchase", "error"}
_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_PROPERTIES = 50


class ValidationError(ValueError):
    """Raised when an event fails schema validation."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC)
    if isinstance(value, str):
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return ts if ts.tzinfo else ts.replace(tzinfo=UTC)
    raise TypeError("timestamp must be ISO-8601 string or epoch seconds")


def validate_event(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate a raw event and return the normalized record.

    Normalized record shape:
        pk          = "USER#<user_id>"
        sk          = "EVENT#<iso_ts>#<event_id>"
        event_type, event_id, user_id, ts, event_date, properties
    """
    errors: list[str] = []

    if not isinstance(raw, dict):
        raise ValidationError(["event must be a JSON object"])

    for field in ("event_id", "user_id", "event_type", "timestamp"):
        if field not in raw or raw[field] in (None, ""):
            errors.append(f"missing required field: {field}")

    event_id = str(raw.get("event_id", ""))
    user_id = str(raw.get("user_id", ""))
    event_type = str(raw.get("event_type", "")).lower()

    if event_id and not _ID_PATTERN.match(event_id):
        errors.append("event_id has invalid characters or length")
    if user_id and not _ID_PATTERN.match(user_id):
        errors.append("user_id has invalid characters or length")
    if event_type and event_type not in ALLOWED_EVENT_TYPES:
        errors.append(f"unsupported event_type: {event_type}")

    ts = None
    if raw.get("timestamp") not in (None, ""):
        try:
            ts = _parse_timestamp(raw["timestamp"])
        except (TypeError, ValueError, OverflowError) as exc:
            errors.append(f"invalid timestamp: {exc}")

    properties = raw.get("properties", {}) or {}
    if not isinstance(properties, dict):
        errors.append("properties must be an object")
    elif len(properties) > MAX_PROPERTIES:
        errors.append(f"properties exceeds {MAX_PROPERTIES} keys")

    if errors:
        raise ValidationError(errors)

    iso_ts = ts.astimezone(UTC).isoformat(timespec="milliseconds")
    return {
        "pk": f"USER#{user_id}",
        "sk": f"EVENT#{iso_ts}#{event_id}",
        "event_id": event_id,
        "user_id": user_id,
        "event_type": event_type,
        "ts": iso_ts,
        "event_date": iso_ts[:10],
        # GSI1: query all events of a type for a given day
        "gsi1pk": f"TYPE#{event_type}#{iso_ts[:10]}",
        "gsi1sk": iso_ts,
        "properties": {str(k): v for k, v in properties.items()},
    }
