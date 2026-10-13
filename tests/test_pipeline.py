import json

import pytest

from src.ingest.handler import handler
from src.ingest.validation import ValidationError, validate_event


class ConditionalCheckFailed(Exception):
    response = {"Error": {"Code": "ConditionalCheckFailedException"}}


class FakeTable:
    """In-memory stand-in for a DynamoDB Table with conditional puts."""

    def __init__(self):
        self.items = {}

    def put_item(self, Item, ConditionExpression=None):
        key = (Item["pk"], Item["sk"])
        if ConditionExpression and key in self.items:
            raise ConditionalCheckFailed()
        self.items[key] = Item


def make_event(**overrides):
    event = {
        "event_id": "evt-001",
        "user_id": "user_42",
        "event_type": "click",
        "timestamp": "2026-10-01T12:00:00Z",
        "properties": {"button": "signup"},
    }
    event.update(overrides)
    return event


def api_request(payload):
    return {"body": json.dumps(payload), "isBase64Encoded": False}


# --- validation -----------------------------------------------------------

def test_validate_builds_keys():
    record = validate_event(make_event())
    assert record["pk"] == "USER#user_42"
    assert record["sk"].startswith("EVENT#2026-10-01T12:00:00.000+00:00#evt-001")
    assert record["gsi1pk"] == "TYPE#click#2026-10-01"
    assert record["event_date"] == "2026-10-01"


def test_validate_accepts_epoch_timestamp():
    record = validate_event(make_event(timestamp=1759320000))
    assert record["event_date"] == "2025-10-01"


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"event_id": ""}, "missing required field: event_id"),
        ({"event_type": "hack"}, "unsupported event_type"),
        ({"user_id": "bad id!"}, "user_id has invalid"),
        ({"timestamp": "not-a-date"}, "invalid timestamp"),
        ({"properties": [1, 2]}, "properties must be an object"),
    ],
)
def test_validate_rejects_bad_input(overrides, message):
    with pytest.raises(ValidationError) as exc:
        validate_event(make_event(**overrides))
    assert any(message in e for e in exc.value.errors)


# --- handler --------------------------------------------------------------

def test_single_event_is_written():
    table = FakeTable()
    resp = handler(api_request(make_event()), table=table)
    assert resp["statusCode"] == 202
    assert json.loads(resp["body"])["accepted"] == ["evt-001"]
    assert len(table.items) == 1
    stored = next(iter(table.items.values()))
    assert stored["expires_at"] > 0


def test_retry_is_idempotent():
    table = FakeTable()
    handler(api_request(make_event()), table=table)
    resp = handler(api_request(make_event()), table=table)
    body = json.loads(resp["body"])
    assert body["duplicates"] == ["evt-001"]
    assert len(table.items) == 1


def test_batch_with_partial_failures():
    table = FakeTable()
    payload = {"events": [make_event(event_id="a"), make_event(event_id="b", event_type="nope")]}
    body = json.loads(handler(api_request(payload), table=table)["body"])
    assert body["accepted"] == ["a"]
    assert body["rejected"][0]["index"] == 1


def test_all_invalid_returns_422():
    resp = handler(api_request(make_event(event_type="nope")), table=FakeTable())
    assert resp["statusCode"] == 422


def test_oversized_batch_rejected():
    payload = {"events": [make_event(event_id=f"e{i}") for i in range(26)]}
    assert handler(api_request(payload), table=FakeTable())["statusCode"] == 413


def test_bad_json_returns_400():
    assert handler({"body": "{not json"}, table=FakeTable())["statusCode"] == 400
