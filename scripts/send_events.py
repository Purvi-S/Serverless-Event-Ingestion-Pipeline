"""Send sample events to the deployed API.

Usage:
    python scripts/send_events.py "$(terraform -chdir=infra output -raw api_endpoint)"
"""

import argparse
import json
import random
import urllib.request
import uuid
from datetime import UTC, datetime

EVENT_TYPES = ["page_view", "click", "signup", "purchase", "error"]


def make_event() -> dict:
    return {
        "event_id": uuid.uuid4().hex,
        "user_id": f"user_{random.randint(1, 500)}",
        "event_type": random.choices(EVENT_TYPES, weights=[60, 25, 5, 5, 5])[0],
        "timestamp": datetime.now(UTC).isoformat(),
        "properties": {"page": random.choice(["/", "/pricing", "/docs", "/checkout"])},
    }


def post(url: str, events: list[dict]) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps({"events": events}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--count", type=int, default=50)
    args = parser.parse_args()

    sent = 0
    while sent < args.count:
        batch = [make_event() for _ in range(min(25, args.count - sent))]
        result = post(args.url, batch)
        sent += len(batch)
        print(f"sent={sent} accepted={len(result['accepted'])} rejected={len(result['rejected'])}")


if __name__ == "__main__":
    main()
