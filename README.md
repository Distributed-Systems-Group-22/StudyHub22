# StudyHub | Content & Metadata Service

Group 22 · COMP41720 Distributed Systems

This repository currently implements the Content & Metadata Service: file upload/storage, owner-only metadata access, soft deletion, batch access checks, and processing-result callbacks. A separate relay publishes upload and deletion events from the PostgreSQL outbox to RabbitMQ. It does not run AI processing, search, or synthesis workers.

## Team responsibilities

The table describes the team's planned service ownership and ADR topics, not features all implemented in this checkout. Only the Content implementation is present; the other services and ADR documents are not included here.

| Team member | Service | Responsibilities | Architecture decision (ADR) |
| --- | --- | --- | --- |
| Chingyun Hsu | Content & Metadata | File storage, metadata, document versions and access, deletion, user-visible processing status, and the planned lightweight calendar | Event-driven Deletion vs Synchronous Deletion |
| Jiaqi Yang | AI Processing | Text extraction, audio transcription, single-document summaries, embeddings, and background jobs | Idempotent Consumers vs Distributed Transactions |
| Limu Zhang | Search & Index | Vector search, index versioning, live permission checks, and stale index cleanup | Live Permission Checks vs Cached Permissions |
| Tzuyu Chang | Synthesis | Cross-document summaries with citations, asynchronous synthesis jobs, cache invalidation, and recovery | On-demand vs Cached Background Summary Generation |

## Repository layout

| Path | Purpose |
| --- | --- |
| `content-service/main.py` | FastAPI routes for documents, permission checks, and AI Processing callbacks |
| `content-service/relay.py` | Background publisher for the PostgreSQL outbox |
| `content-service/migrate.py` | Migration runner with history, checksums, and an advisory lock |
| `content-service/migrations/` | PostgreSQL schema migrations, applied in numbered order |
| `content-service/Dockerfile` | Python 3.12 image shared by API, relay, and migration containers |
| `content-service/.dockerignore` | Excludes local environment and data files from the build context |
| `setup/setup-content-service.ps1`, `setup/setup-content-service.sh` | Create local configuration and fill missing service tokens |
| `setup/start-content-service.ps1`, `setup/start-content-service.sh` | Run Compose in the background |
| `compose.yaml` | PostgreSQL, RabbitMQ, migrations, API, and relay containers |
| `.env.example` | Local configuration template |
| `content-service/requirements.txt` | Python dependencies |

Root `.env`, `uploads/`, and any local `.venv/` are excluded from Git. Compose bind-mounts `./uploads` into the API container at `/data/uploads`; this is a host directory, not a Docker named volume. No `docs/` directory or placeholder directories for the other three services remain in this checkout.

## Run the Content Service locally

Start Docker Desktop with its Linux container engine and open a terminal at the repository root, where `compose.yaml` lives. Confirm `docker compose version` works in that terminal; the scripts require Docker CLI on PATH. Dependencies are installed during image build, and no host virtual environment is required. Each developer uses their own `.env`.

### Windows (PowerShell)

No local Python installation is required for the PowerShell setup.

```powershell
# First-time setup
.\setup\setup-content-service.ps1

# Build and start the Content stack in containers
docker compose up --build -d
```

### macOS (Terminal)

Python should be available through `python3` for the first-time configuration script.

```bash
# First-time setup
bash setup/setup-content-service.sh

# Build and start the Content stack in containers
docker compose up --build -d
```

Setup only prepares configuration: it copies `.env.example` when `.env` is missing and generates missing or blank Processing, Search, and Synthesis tokens. Existing nonempty tokens are preserved. It does not install host dependencies, start Docker, or run migrations. Keep `.env` out of Git and give each calling service only its own matching token.

For subsequent starts, run `docker compose up --build -d` directly; the setup script is only needed to initialize configuration or fill missing tokens. The existing `start-content-service.ps1` and `start-content-service.sh` scripts remain optional shortcuts for the same Compose command. Compose defines these five services:

| Compose service | Purpose | Startup dependency |
| --- | --- | --- |
| `db` | PostgreSQL 17; Content database | None |
| `rabbitmq` | RabbitMQ 4 with management UI | None |
| `content-migrate` | Apply pending SQL migrations, then exit | Healthy `db` |
| `content-api` | FastAPI on port 8000 | Successful `content-migrate` |
| `content-relay` | Publish pending outbox events | Successful `content-migrate` and healthy `rabbitmq` |

The three Content containers use the image `studyhub-content:local`. After setup, you can use these commands directly:

```bash
docker compose up --build -d
docker compose ps -a
docker compose logs --tail 50 content-migrate content-api content-relay
```

`content-migrate` showing `Exited (0)` is normal; it is not a long-running service. Check for API health and the relay's `Relay ready` log. The startup command does not wait for the API's own health check to pass. An API health check only verifies HTTP liveness, not DB access or worker processing.

Open the [API docs](http://127.0.0.1:8000/docs), [OpenAPI JSON](http://127.0.0.1:8000/openapi.json), or [RabbitMQ management UI](http://127.0.0.1:15672/). RabbitMQ login uses `RABBITMQ_DEFAULT_USER` and `RABBITMQ_DEFAULT_PASS` from your local `.env` for the initial broker setup.

Compose constructs container connection URLs using `db:5432` and `rabbitmq:5672`. The `STUDYHUB_DATABASE_URL` and `STUDYHUB_AMQP_URL` entries in `.env.example` are host-development URLs; Compose supplies its own values to the containers. Use URL-safe database/broker credentials because they are interpolated into those URLs. All three service tokens must be nonempty for this Compose configuration. The example enables `STUDYHUB_DEV_IDENTITY=1`; a missing value defaults to `0` in Compose.

Use `docker compose logs -f content-api content-relay` to follow logs. Containers run in the background; Ctrl+C only stops following logs. Use `docker compose down` to stop the stack while retaining database and broker volumes. Do not add `-v` when preserving data.

## HTTP integration

Use `http://127.0.0.1:8000` from the host and `http://content-api:8000` from containers on the same Compose network. There is no Gateway, login endpoint, or user registration in this repository. With `STUDYHUB_DEV_IDENTITY=1`, send `User_Name: alice` or `User_Name: bob` on user document routes. Internal routes use service tokens as described below.

| Method and path | Caller | Request and result |
| --- | --- | --- |
| `GET /health` | Local checks | No authentication. Returns `200` with `{"status":"ok"}` when the API responds; does not check DB or RabbitMQ. |
| `POST /documents` | Local user | `User_Name` and a multipart field named `file`, up to 5 MiB. Returns `201` with `documentId`, `originalFilename`, and `sizeBytes`. |
| `GET /documents/{document_id}` | Local user | `User_Name`. Returns `200` with metadata, `documentVersion`, and `processingStatus`, or `404` for a missing, deleted, or inaccessible document. |
| `DELETE /documents/{document_id}` | Local user | `User_Name`. The owner can soft-delete an active document. Returns `204` on success or `404` when no accessible active document matches. |
| `GET /internal/documents/{document_id}/versions/{document_version}/file` | AI Processing | Processing bearer token. Returns `200` with binary file content and the original filename in `Content-Disposition`. Returns `404` for a missing, deleted, or stale version. |
| `PUT /internal/documents/{document_id}/versions/{document_version}/processing-status` | AI Processing | Processing bearer token and JSON such as `{"status":"succeeded"}`. The worker can report `succeeded` or `failed`. Returns `204` for an accepted or repeated identical result, `404` for an unavailable version, or `409` for a conflicting final result. |
| `POST /internal/documents/access-check` | Search & Index, Synthesis | The caller's service bearer token, `User_Name`, and JSON `{"documentIds":[...]}` with 1–100 UUIDs. Returns `200` with `{"documents":[...]}`. Each entry contains `documentId` and `documentVersion`. |

New uploads start at `pending` and version `1`. Without an external worker or a manual callback, they remain `pending`. The API records the status supplied by the Processing caller; it does not run AI or independently verify its output. That status does not establish Search index readiness.

### Authentication and request conventions

| Caller | Required headers | Configuration |
| --- | --- | --- |
| Local user | `User_Name: alice` or `User_Name: bob` | Requires `STUDYHUB_DEV_IDENTITY=1`; this is development identity, not Gateway authentication. |
| AI Processing | `Authorization: Bearer <processing-token>` | Token must match `STUDYHUB_PROCESSING_TOKEN`. No user header is required on the two Processing endpoints. |
| Search / Synthesis | `Authorization: Bearer <caller-token>` and `User_Name: <authenticated-user>` | Token must match `STUDYHUB_SEARCH_TOKEN` or `STUDYHUB_SYNTHESIS_TOKEN`. User header length: 1–128 characters. |
| Health check | None | Public HTTP liveness check. |

Use the exact header name `User_Name` (underscore). Service tokens identify trusted callers; Search and Synthesis must derive the user header from their authenticated request context. The Processing token grants access to active document versions without an owner header.
In Swagger UI, enter only the token value under `ProcessingToken` or `DocumentAccessToken`; Swagger constructs the Bearer header. For direct HTTP requests, send `Authorization: Bearer <token>`. A user upload/read/delete needs only `User_Name`, not a service token.

JSON field names use camelCase. Path `document_id` values must be UUIDs; `document_version` must be an integer greater than or equal to 1. JSON requests use `Content-Type: application/json`; upload uses `multipart/form-data` with a boundary generated by the HTTP client.

Upload accepts a nonempty file up to **5,242,880 bytes (5 MiB)**. The current implementation does not restrict extensions or validate MIME types. Each upload creates a new UUID, version `1`, and processing status `pending`; upload success does not mean AI processing has finished.

Example upload response (`201`):

```json
{
  "documentId": "04a1dc78-a5d7-428a-8773-3ba9ec503c22",
  "originalFilename": "lecture.pdf",
  "sizeBytes": 2048
}
```

Example metadata response (`200`):

```json
{
  "documentId": "04a1dc78-a5d7-428a-8773-3ba9ec503c22",
  "originalFilename": "lecture.pdf",
  "sizeBytes": 2048,
  "documentVersion": 1,
  "processingStatus": "pending"
}
```

File download returns `application/octet-stream` and a `Content-Disposition` filename derived from the original filename. It returns binary content, not JSON.

Processing status request:

```json
{"status":"succeeded"}
```

Only `succeeded` and `failed` are accepted. The permitted transitions are `pending → succeeded` or `pending → failed`. Repeating the same final result returns `204`; changing a final result returns `409`. This endpoint does not reset jobs or emit an outbox event. `succeeded` describes AI processing completion, not Search index readiness.

Batch access request (1–100 UUIDs):

```json
{"documentIds":["04a1dc78-a5d7-428a-8773-3ba9ec503c22"]}
```

Example response:

```json
{
  "documents": [
    {"documentId":"04a1dc78-a5d7-428a-8773-3ba9ec503c22","documentVersion":1}
  ]
}
```

Only active documents owned by the supplied user are returned. Missing, deleted, and unauthorized IDs are omitted; no readable matches returns `{"documents":[]}` with `200`. Results have no guaranteed order, and duplicate input IDs do not produce duplicate rows. Match by ID and compare the returned version with the candidate's source version. Callers must fail closed on timeout or non-`200` responses and must not serve unchecked content.

### Error semantics

Explicit application errors use a JSON `detail` string, for example:

```json
{"detail":"Document not found."}
```

- `401`: missing/invalid service bearer token, or missing/invalid local user identity.
- `400`: the upload handler rejects an empty file or a missing filename. A missing multipart `file` field fails validation with `422` instead.
- `404`: inaccessible resources are indistinguishable from missing resources on user document routes. A repeated deletion also returns `404`.
- `409`: a Processing callback conflicts with an existing terminal status.
- `413`: uploaded file exceeds 5 MiB.
- `422`: request validation failure, such as invalid UUID/version, missing required fields, invalid status, or an access-check list outside 1–100 entries. FastAPI returns a `detail` array with validation information.
- `503`: required authentication configuration is unavailable. For local user routes, development identity is disabled; for internal routes, the relevant token configuration is missing.
- Unhandled database/storage failures can return `500`; the application does not normalize all failures into the JSON error format or map dependency outages to `503`.

## Database specification

Content uses PostgreSQL 17. With the example configuration, database and user are both `studyhub`; actual values come from `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` in root `.env`.

| Connection / storage | Location |
| --- | --- |
| Host database tools | `127.0.0.1:5433` |
| API, relay, and migration containers | `db:5432` |
| PostgreSQL persistence | Compose volume key `postgres-data`, normally named `<project>_postgres-data`, mounted at `/var/lib/postgresql/data` |
| Original file persistence | Root `uploads/`, mounted at `/data/uploads` in API only |

Only Content processes access this database. Other services must use Content APIs/events and maintain their own databases. Original file bytes are not stored in PostgreSQL.

### `documents`

One row represents one document's current metadata. There is no version-history table.

| Column | PostgreSQL type | Nullable | Default / constraint | Meaning |
| --- | --- | --- | --- | --- |
| `id` | `UUID` | No | Primary key; generated by application | Document identifier; also the stored filename |
| `original_filename` | `TEXT` | No | No default | Original upload filename |
| `size_bytes` | `INTEGER` | No | `CHECK (size_bytes > 0)` | File size; the 5 MiB maximum is enforced by API, not DB |
| `owner_id` | `TEXT` | No | No default | User identity; no users table or foreign key |
| `version` | `INTEGER` | No | `DEFAULT 1`, `CHECK (version > 0)` | Current document version; replacement is not implemented |
| `deleted_at` | `TIMESTAMPTZ` | Yes | Null when active | Soft-deletion timestamp |
| `processing_status` | `TEXT` | No | `DEFAULT 'pending'`; allowed: `pending`, `succeeded`, `failed` | User-visible processing result |

Files are stored at `<STUDYHUB_UPLOAD_DIR>/<id>` without their original extension. Soft deletion retains both the row and the physical file. The schema currently has no document creation/update timestamps, sharing table, or calendar table.

### `outbox_events`

| Column | PostgreSQL type | Nullable | Default / constraint | Meaning |
| --- | --- | --- | --- | --- |
| `event_id` | `UUID` | No | Primary key; generated by application | Stable deduplication identifier |
| `event_type` | `TEXT` | No | No DB enum/check | Currently `document.uploaded` or `document.deleted` |
| `payload` | `JSONB` | No | No JSON schema constraint | Application writes `documentId` and `documentVersion` |
| `created_at` | `TIMESTAMPTZ` | No | `DEFAULT CURRENT_TIMESTAMP` | Event creation time |
| `published_at` | `TIMESTAMPTZ` | Yes | Null until published | Recorded after broker-confirmed publication |

The document reference is inside JSON; there is no foreign key to `documents`. Relay adds `eventId` and `eventType` to the payload when publishing. `published_at` is recorded in PostgreSQL after broker confirmation; a broker-confirmed event can still have a null value if the DB commit fails. It does not record consumer completion. Published events are currently retained; there is no automatic purge.

### `schema_migrations`

Created by `content-service/migrate.py`, rather than a numbered SQL migration.

| Column | PostgreSQL type | Nullable | Default / constraint | Meaning |
| --- | --- | --- | --- | --- |
| `name` | `TEXT` | No | Primary key | Applied SQL filename |
| `checksum` | `TEXT` | No | No default | SHA-256 of decoded SQL text encoded as UTF-8 |
| `applied_at` | `TIMESTAMPTZ` | No | `DEFAULT NOW()` | Migration application time |

The current schema defines primary-key indexes only; no additional indexes or cross-table foreign keys are declared.

The migration runner applies numbered SQL files under an advisory lock and records each migration in the same transaction as its schema changes. Existing databases without migration history run the current idempotent SQL once to register it; migration 002 assigns legacy ownerless documents to Alice. Add a new numbered file for future schema changes rather than editing an applied migration, because checksum mismatches stop startup.

Keep the same Compose project name when reusing existing volumes. Renaming the checkout can change the default project name and select different volumes; use `docker compose -p <previous-project-name>` when necessary.

### Transactions and consistency

- Upload inserts document metadata and `document.uploaded` into the same DB transaction. File writing occurs before commit but is not transactional; a later failure can leave an orphan file.
- Delete sets `deleted_at` and inserts `document.deleted` in one transaction. Content access checks exclude the document after commit; downstream cleanup is asynchronous.
- Processing callbacks lock the document with `FOR UPDATE` before checking/updating status, preserving the terminal-result rule under concurrent callbacks.
- Relay selects unpublished events with `FOR UPDATE SKIP LOCKED`. It publishes with broker confirms before marking the row published. A crash after publication but before DB commit can cause redelivery; consumers must deduplicate by `eventId`. Multiple relays do not guarantee event order.

For database inspection, run this from the repository root (the container expands its configured credentials):

```bash
docker compose exec db sh -c 'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Inside `psql`, useful read-only checks are:

```sql
\dt
\d documents
\d outbox_events
SELECT name, applied_at FROM schema_migrations ORDER BY name;
SELECT COUNT(*) AS unpublished_events FROM outbox_events WHERE published_at IS NULL;
```

## RabbitMQ integration

The relay declares the durable topic exchange `document.events` and the three durable queues/bindings below. It publishes persistent JSON messages with publisher confirms and `mandatory=True`; the routing key matches `eventType`, and the AMQP `message_id` is `eventId`. The consumers in the table are intended downstream callers, not containers included in this Compose stack.

| Event | Queue | Consumer | Expected action |
| --- | --- | --- | --- |
| `document.uploaded` | `document.jobs` | AI Processing | Fetch the file using the ID and version, process it, and report the final result. |
| `document.deleted` | `search.document-events` | Search & Index | Remove or invalidate the document's index entries. |
| `document.deleted` | `synthesis.document-events` | Synthesis | Invalidate cached results derived from the document. |

```json
{
  "eventId": "1fc17bd4-9a02-4d10-a168-562bd3fd1b24",
  "eventType": "document.uploaded",
  "documentId": "04a1dc78-a5d7-428a-8773-3ba9ec503c22",
  "documentVersion": 1
}
```

The relay can resend an event with the same `eventId`, so consumers should handle duplicates. The AI worker should stop processing that ID and version if fetching the file returns `404`. A soft deletion takes effect in Content as soon as its database transaction commits. The deletion event then lets downstream services clean up their own data.

The relay publishes one pending event per transaction. On caught AMQP or PostgreSQL errors, it reconnects after a fixed three-second delay with no retry limit; it does not implement exponential backoff or a dead-letter policy. When no event is pending, it waits one second. A RabbitMQ outage can leave events pending while the API continues accepting writes if PostgreSQL and file storage are available.

Without external consumers, messages remain queued and no AI output, search index, or synthesis cache is produced. This relay does not declare `index.jobs` or `synthesis.jobs`, and Content does not emit permission-change or version-replacement events yet.

## Smoke test

These steps test the Content API and publication path, using manual requests in place of the missing downstream workers. Start the stack, confirm API availability, and obtain your local Processing and Search/Synthesis tokens from `.env`. Use a synthetic nonempty file of at most 5 MiB. The steps below are a repeatable checklist, not evidence that an AI worker processed the file.

1. In `/docs`, upload a synthetic PDF with `User_Name: alice`. Expect `201` and copy the `documentId`.
2. Use the same ID to fetch metadata. Expect `200` for Alice and `404` for Bob.
3. With `DocumentAccessToken`, send the ID to the batch access route. Expect the ID and version for `User_Name: alice` and an empty list for `bob`.
4. With `ProcessingToken`, fetch version `1` and manually report `{"status":"succeeded"}`. Expect `200` for the download and `204` for the report. Alice's metadata should now show `succeeded`. Repeat the same callback: expect `204`; send `failed` afterward: expect `409`.
5. Delete the file as Alice. Expect `204`, then retry the worker download and batch access check. Expect `404` for the download and an empty access list. The relay should log publication of the upload and deletion events.
6. Check `docker compose logs content-relay` and the three queues in RabbitMQ management. Publication and queued messages verify the broker path, not downstream completion. With no consumers, messages accumulate in these queues.

## Current handoff scope

Implemented here: containerized Content API and relay, PostgreSQL/RabbitMQ infrastructure, tracked SQL migrations, owner-only upload/read/soft-delete, version-checked internal file retrieval, processing-result callbacks, batch access checks, and upload/deletion outbox events. The root Compose file is executable for this Content stack; integration of the other services is still pending.

Not implemented here: AI Processing/Search/Synthesis services or their consumers and databases, Gateway/login, frontend, document listing, replacing a document version, sharing or permission updates, calendar, physical file cleanup, Prometheus/Grafana monitoring, and automated test suites. The `version` field and version checks exist, but all uploads currently create a new document at version `1`. A document's deleted row and original file remain stored.

Consumers still need their own idempotency, retries, permission/version checks, and derived-data cleanup. The repository provides the Content endpoints and events for those integrations; it does not demonstrate the full four-service workflow on its own.
