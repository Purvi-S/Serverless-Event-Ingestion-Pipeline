"""Lambda entry point: API Gateway (HTTP API) -> validate -> DynamoDB.

Accepts either a single event object or {"events": [...]} (max 25 per request).
Writes are idempotent: a conditional put on (pk, sk) means retries from
clients or API Gateway never create duplicates.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from .validation import ValidationError, validate_event

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

TABLE_NAME = os.environ.get("TABLE_NAME", "app-events")
TTL_DAYS = int(os.environ.get("TTL_DAYS", "90"))
MAX_BATCH = 25

_table = None


def _get_table():
    global _table
    if _table is None:
        import boto3

        _table = boto3.resource("dynamodb").Table(TABLE_NAME)
    return _table


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _emit_metrics(accepted: int, rejected: int, duplicates: int) -> None:
    """CloudWatch Embedded Metric Format: logged JSON becomes custom metrics."""
    print(
        json.dumps(
            {
                "_aws": {
                    "Timestamp": int(time.time() * 1000),
                    "CloudWatchMetrics": [
                        {
                            "Namespace": "EventPipeline",
                            "Dimensions": [["Service"]],
                            "Metrics": [
                                {"Name": "EventsAccepted", "Unit": "Count"},
                                {"Name": "EventsRejected", "Unit": "Count"},
                                {"Name": "EventsDuplicate", "Unit": "Count"},
                            ],
                        }
                    ],
                },
                "Service": "ingest",
                "EventsAccepted": accepted,
                "EventsRejected": rejected,
                "EventsDuplicate": duplicates,
            }
        )
    )


def _parse_body(event: dict[str, Any]) -> list[dict[str, Any]]:
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        import base64

        body = base64.b64decode(body).decode("utf-8")
    payload = json.loads(body)
    if isinstance(payload, dict) and "events" in payload:
        items = payload["events"]
        if not isinstance(items, list):
            raise ValueError("'events' must be a list")
        return items
    return [payload]


def _is_conditional_failure(exc: Exception) -> bool:
    response = getattr(exc, "response", None) or {}
    return response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"


def handler(event: dict[str, Any], context: Any = None, table=None) -> dict[str, Any]:
    table = table or _get_table()

    try:
        items = _parse_body(event)
    except (ValueError, json.JSONDecodeError) as exc:
        return _response(400, {"error": f"invalid JSON body: {exc}"})

    if not items:
        return _response(400, {"error": "no events supplied"})
    if len(items) > MAX_BATCH:
        return _response(413, {"error": f"batch size exceeds {MAX_BATCH}"})

    accepted, duplicates, rejected = [], [], []
    expires_at = int(time.time()) + TTL_DAYS * 86400

    for index, raw in enumerate(items):
        try:
            record = validate_event(raw)
        except ValidationError as exc:
            rejected.append({"index": index, "errors": exc.errors})
            continue

        record["expires_at"] = expires_at
        try:
            table.put_item(
                Item=record,
                ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
            )
            accepted.append(record["event_id"])
        except Exception as exc:  # botocore ClientError
            if _is_conditional_failure(exc):
                duplicates.append(record["event_id"])
            else:
                logger.exception("DynamoDB write failed for event %s", record["event_id"])
                raise  # let Lambda/API Gateway surface a 5xx; client retry is idempotent

    _emit_metrics(len(accepted), len(rejected), len(duplicates))
    logger.info(
        "batch processed accepted=%d duplicates=%d rejected=%d",
        len(accepted), len(duplicates), len(rejected),
    )

    status = 202 if accepted or duplicates else 422
    return _response(
        status,
        {"accepted": accepted, "duplicates": duplicates, "rejected": rejected},
    )
