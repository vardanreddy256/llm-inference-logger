# LLM Inference Logging System

A production-grade inference logging and ingestion system for LLM applications. Supports multi-turn chat with OpenAI, Anthropic, and Google Gemini, with real-time observability dashboards.

---

## Quick Start (one command)

```bash
cp .env.example .env        # add at least one API key
docker compose up --build   # starts all 5 services
```

Open **http://localhost:3000** — the app is ready.

---

## Architecture Overview

```
┌─────────────┐     SSE stream      ┌──────────────────────┐
│   Frontend  │ ◄──────────────────► │  Backend (FastAPI)   │
│  React/TS   │   REST (convs, chat) │  :8000               │
│  :3000      │                      │                      │
└─────────────┘                      │  ┌────────────────┐  │
                                     │  │  LLM SDK/Wrap  │  │
                                     │  │  • OpenAI      │  │
                                     │  │  • Anthropic   │  │
                                     │  │  • Gemini      │  │
                                     │  └───────┬────────┘  │
                                     └──────────┼───────────┘
                                                │ xadd (fire-and-forget)
                                                ▼
                                     ┌──────────────────────┐
                                     │  Redis Streams       │
                                     │  "inference_events"  │
                                     └──────────┬───────────┘
                                                │ xreadgroup
                                                ▼
                                     ┌──────────────────────┐
                                     │  Ingestion Service   │
                                     │  (FastAPI) :8001     │
                                     │  • validate/parse    │
                                     │  • write to Postgres │
                                     │  • metrics REST API  │
                                     └──────────┬───────────┘
                                                │
                                                ▼
                                     ┌──────────────────────┐
                                     │  PostgreSQL          │
                                     │  • conversations     │
                                     │  • messages          │
                                     │  • inference_logs    │
                                     └──────────────────────┘
```

### Ingestion Flow

1. User sends a message → Backend streams the LLM response via SSE.
2. The **LLM SDK Wrapper** (`backend/app/sdk/llm_wrapper.py`) wraps every provider call, timing it from start to first byte through final token.
3. On completion (or error), the wrapper fires an `asyncio.create_task` to `XADD` an event to the `inference_events` Redis Stream. This is **non-blocking** — it never adds latency to the user response.
4. The **Ingestion Service** runs a **consumer group** loop (`XREADGROUP`) polling the stream in batches of 50. Each event is validated with Pydantic, PII-redacted fields checked, then written to `inference_logs`. Successfully processed events are `XACK`'d; failures are left unacknowledged for retry.
5. The Ingestion Service also exposes `/metrics/*` endpoints that the frontend dashboard polls every 15 seconds.

---

## Services

| Service | Port | Description |
|---|---|---|
| frontend | 3000 | React + TypeScript chat UI + dashboard |
| backend | 8000 | FastAPI — chat, conversations, streaming |
| ingestion-service | 8001 | FastAPI — event consumer + metrics API |
| postgres | 5432 | Shared database |
| redis | 6379 | Event bus (Redis Streams) |

---

## Schema Design

### `conversations`
Stores each chat session. `session_id` is the stable public-facing identifier (UUID string), separate from the internal PK so the PK type can change without breaking clients. `status` drives the cancel/resume workflow. `provider` and `model` are captured at creation time so historical logs remain accurate even if the user switches provider mid-session.

```sql
id          UUID PK
session_id  VARCHAR UNIQUE  -- public-facing, stable
title       VARCHAR         -- auto-set from first user message (80 chars)
provider    VARCHAR         -- openai | anthropic | gemini
model       VARCHAR         -- exact model string
status      VARCHAR         -- active | cancelled | completed
created_at  TIMESTAMPTZ
updated_at  TIMESTAMPTZ     -- updated on every new message
extra_metadata  JSONB       -- forward-compatible extension point
```

### `messages`
Individual turns. `sequence_number` is explicit (not derived from `created_at`) so ordering is deterministic even under bulk inserts. `content_preview` (500 chars) allows list views without loading full content. Full `content` is stored for context rebuilding.

```sql
id               UUID PK
conversation_id  UUID FK → conversations.id (CASCADE DELETE)
role             VARCHAR  -- user | assistant | system
content          TEXT     -- full message
content_preview  VARCHAR  -- first 500 chars for list views
sequence_number  INTEGER  -- explicit ordering
created_at       TIMESTAMPTZ
extra_metadata   JSONB
```

### `inference_logs`
Append-only observability store. FK to `conversations` uses `SET NULL` on delete so metrics survive conversation deletion. `input_preview` and `output_preview` are **PII-redacted** before storage. `raw_metadata` holds the original event_id and timestamp from Redis for audit trails.

```sql
id                UUID PK
conversation_id   UUID FK → conversations.id (SET NULL)
message_id        UUID     -- soft reference, no FK (avoids cross-service coupling)
provider          VARCHAR INDEX
model             VARCHAR
status            VARCHAR INDEX  -- success | error
latency_ms        FLOAT
prompt_tokens     INTEGER
completion_tokens INTEGER
total_tokens      INTEGER
input_preview     TEXT  -- PII-redacted, ≤200 chars
output_preview    TEXT  -- PII-redacted, ≤200 chars
error_message     TEXT
request_id        VARCHAR INDEX
timestamp         TIMESTAMPTZ INDEX
raw_metadata      JSONB
```

**Why no FK on `message_id`?** The ingestion service is a separate process writing asynchronously. A hard FK would create a cross-service write-ordering constraint and require distributed transactions. The soft reference is sufficient for dashboard queries.

---

## Tradeoffs Made

| Decision | Chosen | Rejected | Reason |
|---|---|---|---|
| Event bus | Redis Streams | Kafka / RabbitMQ | Redis is already a common dependency; Streams give consumer groups + at-least-once without a separate broker |
| Event publishing | `asyncio.create_task` (fire-and-forget) | Synchronous HTTP POST | Zero added latency to user response; acceptable if Redis is briefly unavailable |
| PII redaction | Regex on preview only | Full message scan | Full scan adds latency; previews are the only thing logged to persistent storage |
| Context window | Last 20 messages | All messages | Prevents unbounded token costs; configurable constant |
| Ingestion consumer | Single consumer per instance | Multiple parallel consumers | Simplicity; can scale by running multiple ingestion-service replicas with the same group name |
| DB schema | Separate `inference_logs` table | Inline on `messages` | Decouples observability from chat storage; logs survive message/conversation deletion |
| Streaming | SSE (Server-Sent Events) | WebSockets | SSE is unidirectional, simpler, and works with standard HTTP proxies |

---

## What I Would Improve With More Time

1. **Alembic migrations** — currently tables are created via `Base.metadata.create_all`. Production needs versioned migrations for zero-downtime schema changes.
2. **Dead-letter queue** — unacknowledged Redis Stream events should be moved to a DLQ (separate stream) after N retries, with alerting.
3. **Cost tracking** — map token counts to per-provider pricing tables and expose a cost dashboard.
4. **Structured logging** — replace `logging.basicConfig` with `structlog` for JSON log lines, making it easier to ship to Datadog/Loki.
5. **Auth** — add JWT/session auth to protect the chat and metrics APIs.
6. **Rate limiting** — per-user or per-session request throttling on the backend to prevent runaway API spend.
7. **Streaming token counting** — some providers don't emit token counts mid-stream; a tiktoken fallback would give accurate counts on the final chunk.
8. **Kubernetes manifests** — Helm chart or kustomize overlays for self-hosted k8s deployment (mentioned in bonus).
9. **End-to-end tests** — pytest + httpx async test suite covering the full chat → ingest → metrics round-trip.
10. **OpenTelemetry** — instrument spans and export traces to Jaeger/Grafana Tempo for distributed tracing.

---

## Architecture Notes

### Logging Strategy
The SDK wrapper captures metadata at the boundaries of the LLM call: start timestamp, end timestamp, provider response fields (tokens, model, request ID). PII redaction runs on the preview text before the event is constructed. The event is published asynchronously to Redis — if Redis is down, the error is logged at WARNING level and the user response is unaffected. The ingestion service can also receive events via a direct `/ingest` HTTP endpoint as a fallback.

### Scaling Considerations
- **Backend**: Stateless FastAPI; scale horizontally behind a load balancer. SSE connections are long-lived, so a sticky-session LB or a message-passing layer (Redis pub/sub) would be needed if sessions must be resumed on a different pod.
- **Ingestion**: Multiple ingestion-service replicas can share the same Redis consumer group (`ingestion-group`). Each replica independently claims and acks messages — no coordination needed.
- **Redis Streams**: `MAXLEN ~10000` on the stream caps memory use. For high-throughput scenarios, increase this or add a separate archival consumer.
- **Postgres**: Add read replicas for the metrics API to avoid contention with the write path. The `inference_logs` table is append-only, making it an ideal candidate for TimescaleDB hypertable compression.

### Failure Handling Assumptions
- **Redis down**: SDK publishing fails silently; user chat is unaffected. Metrics may lag. Recovery: direct `/ingest` fallback endpoint.
- **Ingestion DB write fails**: Event remains unacknowledged in Redis Stream and will be retried on next poll. Idempotency is not currently enforced (could produce duplicate rows on retry — fixable with a unique index on `raw_metadata->>'event_id'`).
- **LLM provider error**: Captured as `status=error` with `error_message` field. The user sees an error in the UI. The inference log is still published for observability.
- **Frontend / backend disconnect**: SSE reconnects automatically (browser EventSource). Chat state is server-side; refreshing the page restores conversation history.

---

## Local Development (without Docker)

```bash
# 1. Start infra
docker compose up postgres redis -d

# 2. Backend
cd backend
pip install -r requirements.txt
cp ../.env.example .env  # fill in API keys
uvicorn app.main:app --reload --port 8000

# 3. Ingestion service
cd ../ingestion-service
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001

# 4. Frontend
cd ../frontend
npm install
npm run dev   # http://localhost:3000
```

---

## API Reference

### Backend (`:8000`)
| Method | Path | Description |
|---|---|---|
| POST | `/api/chat` | Stream or non-stream chat (SSE) |
| GET | `/api/conversations` | List conversations |
| POST | `/api/conversations` | Create conversation |
| GET | `/api/conversations/:id` | Get conversation |
| GET | `/api/conversations/:id/messages` | Get messages |
| POST | `/api/conversations/:id/cancel` | Cancel conversation |
| POST | `/api/conversations/:id/resume` | Resume conversation |
| GET | `/api/providers` | List available providers |

### Ingestion Service (`:8001`)
| Method | Path | Description |
|---|---|---|
| POST | `/ingest` | Direct event ingest (fallback) |
| GET | `/metrics/summary` | Aggregate stats (window: 1h/6h/24h/7d) |
| GET | `/metrics/latency` | Latency time series |
| GET | `/metrics/throughput` | Requests per minute |
| GET | `/metrics/errors` | Recent errors |
| GET | `/metrics/by-provider` | Per-provider breakdown |
