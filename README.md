# Serverless Event Ingestion Pipeline


An event-driven pipeline on AWS. Applications send events through **API Gateway**. A **Lambda** function validates and normalizes each event, then writes it to **DynamoDB**. **CloudWatch** handles metrics, alarms, and the dashboard. **Terraform** provisions all of it.

```
client ──POST /events──▶ API Gateway (HTTP API, throttled)
                              │
                              ▼
                        Lambda (Python 3.12, arm64)
                        • schema validation
                        • normalization + key building
                        • idempotent conditional writes
                        • EMF custom metrics
                              │
                              ▼
                        DynamoDB (on-demand, PITR, TTL)
                              │
CloudWatch alarms ──▶ SNS ──▶ email
```

## Design decisions

| Concern | Approach |
|---|---|
| **Access patterns** | Single-table design. `pk=USER#id`, `sk=EVENT#ts#event_id` gives each user's timeline in time order. `GSI1 (TYPE#type#date, ts)` returns every event of one type for a given day without a scan. |
| **Duplicates / retries** | A conditional `PutItem` with `attribute_not_exists` makes client retries safe. Duplicates are counted, not stored. |
| **Bad input** | Each event in a batch is validated on its own. Valid events are written. Invalid ones come back with per-field errors (`202` for partial success, `422` when every event fails). |
| **Fault tolerance** | A DynamoDB failure raises, so the client gets a 5xx and retries. The idempotent writes mean the retry can't create duplicates. |
| **Cost / retention** | On-demand billing. A TTL expires events after 90 days (configurable). |
| **Observability** | Custom metrics (accepted / rejected / duplicate) go out in Embedded Metric Format, with no extra API calls. Alarms cover Lambda errors, p99 latency, API 5xx, and a rejection rate above 10%. |
| **Security** | The Lambda's IAM role can only call `PutItem` on one table and write its own logs. Encryption at rest. X-Ray tracing. |

## Layout

```
src/ingest/handler.py      Lambda entry point
src/ingest/validation.py   schema validation + key design
infra/                     Terraform: API GW, Lambda, DynamoDB, IAM, CloudWatch, SNS
tests/                     pytest unit tests (in-memory DynamoDB fake)
scripts/send_events.py     load generator for a deployed stack
```

## Run locally

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Deploy

```bash
cd infra
terraform init
terraform apply -var="alert_email=you@example.com"
python ../scripts/send_events.py "$(terraform output -raw api_endpoint)" --count 200
```

To tear down: `terraform destroy`.

## API

`POST /events` takes a single event or `{"events": [...]}` (max 25).

```json
{
  "event_id": "a1b2c3",
  "user_id": "user_42",
  "event_type": "click",
  "timestamp": "2026-10-01T12:00:00Z",
  "properties": {"button": "signup"}
}
```

Response:

```json
{"accepted": ["a1b2c3"], "duplicates": [], "rejected": []}
```
