# StudyHub | Content & Metadata Service

Group 22 · COMP41720 Distributed Systems

The Content & Metadata Service stores uploaded files and their metadata, enforces document ownership, and tracks AI processing results. A separate relay publishes upload and deletion events from the PostgreSQL outbox to RabbitMQ.

## Team responsibilities

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
| `content-service/migrations/` | PostgreSQL schema migrations, applied in numbered order |
| `setup/` | Setup and startup scripts for Windows and macOS |
| `compose.yaml` | PostgreSQL, RabbitMQ, migrations, API, and relay containers |
| `.env.example` | Local configuration template |
| `content-service/requirements.txt` | Python dependencies |

The setup scripts create `.env` at the repository root. Compose mounts root `uploads/` into the API container at `/data/uploads`. These local files and directories are excluded from Git. `content-service/Dockerfile` builds the shared API, relay, and migration image; `content-service/migrate.py` applies the SQL migrations.

## Run the Content Service locally

Open Docker Desktop and open a new terminal at the repository root. Docker Compose runs the service and installs Python dependencies inside the image. Each developer uses their own `.env`.

### Windows (PowerShell)

No local Python installation is required for the PowerShell setup.

```powershell
# First-time setup
.\setup\setup-content-service.ps1

# Start the API and relay
.\setup\start-content-service.ps1
```

### macOS (Terminal)

Python should be available through `python3` for the first-time configuration script.

```bash
# First-time setup
bash setup/setup-content-service.sh

# Start the API and relay
bash setup/start-content-service.sh
```

Setup creates `.env` from `.env.example` if needed and fills missing service tokens. Compose builds the image and applies the SQL migrations before starting the API and relay. Existing tokens are preserved. Keep `.env` out of Git and give each calling service only its own matching token.

The startup script runs `docker compose up --build -d`. PostgreSQL and RabbitMQ run in containers; the API waits for successful migrations, and relay additionally waits for RabbitMQ. Open the [API docs](http://127.0.0.1:8000/docs), [OpenAPI JSON](http://127.0.0.1:8000/openapi.json), or [RabbitMQ management UI](http://127.0.0.1:15672/). Use your local RabbitMQ credentials from `.env`.

Use `docker compose logs -f content-api content-relay` to follow logs. Containers run in the background; Ctrl+C only stops following logs. Use `docker compose down` to stop the stack while retaining database and broker volumes. Do not add `-v` when preserving data.

## HTTP integration

Use `http://127.0.0.1:8000` when running the API and the caller on the same host; containers use `http://content-api:8000`. Alice and Bob can test without logging in. The `/internal/` routes are for service-to-service calls. For local user document routes, set `User_Name` to `alice` or `bob` with `STUDYHUB_DEV_IDENTITY=1`. The internal access-check route uses the same header name and requires a service bearer token.

| Method and path | Caller | Request and result |
| --- | --- | --- |
| `GET /health` | Local checks | Returns `200` with `{"status":"ok"}` when the API responds. |
| `POST /documents` | Local user | `User_Name` and a multipart field named `file`, up to 5 MiB. Returns `201` with `documentId`, `originalFilename`, and `sizeBytes`. |
| `GET /documents/{document_id}` | Local user | `User_Name`. Returns `200` with metadata, `documentVersion`, and `processingStatus`, or `404` for a missing, deleted, or inaccessible document. |
| `DELETE /documents/{document_id}` | Local user | `User_Name`. The owner can soft-delete an active document. Returns `204` on success or `404` when no accessible active document matches. |
| `GET /internal/documents/{document_id}/versions/{document_version}/file` | AI Processing | Processing bearer token. Returns `200` with binary file content and the original filename in `Content-Disposition`. Returns `404` for a missing, deleted, or stale version. |
| `PUT /internal/documents/{document_id}/versions/{document_version}/processing-status` | AI Processing | Processing bearer token and JSON such as `{"status":"succeeded"}`. The worker can report `succeeded` or `failed`. Returns `204` for an accepted or repeated identical result, `404` for an unavailable version, or `409` for a conflicting final result. |
| `POST /internal/documents/access-check` | Search & Index, Synthesis | The caller's service bearer token, `User_Name`, and JSON `{"documentIds":[...]}` with 1–100 UUIDs. Returns `200` with `{"documents":[...]}`. Each entry contains `documentId` and `documentVersion`. |

For an internal request, send the configured service token as `Authorization: Bearer <token>`. Use `ProcessingToken` or `DocumentAccessToken` in Swagger UI. For batch access checks, derive `User_Name` from the authenticated user context in the calling service. Match the returned entries by ID and use only entries whose current version matches the candidate version. A `200` with an empty list means no candidate can be used. On a timeout or non-`200` response, withhold the unchecked results.

New uploads start at `pending` and version `1`. A processing status of `succeeded` means AI processing completed. Search index readiness is tracked separately by Search & Index.

### Authentication and request conventions

| Caller | Required headers | Configuration |
| --- | --- | --- |
| Local user | `User_Name: alice` or `User_Name: bob` | Requires `STUDYHUB_DEV_IDENTITY=1`; this is development identity, not Gateway authentication. |
| AI Processing | `Authorization: Bearer <processing-token>` | Token must match `STUDYHUB_PROCESSING_TOKEN`. No user header is required on the two Processing endpoints. |
| Search / Synthesis | `Authorization: Bearer <caller-token>` and `User_Name: <authenticated-user>` | Token must match `STUDYHUB_SEARCH_TOKEN` or `STUDYHUB_SYNTHESIS_TOKEN`. User header length: 1–128 characters. |
| Health check | None | Public HTTP liveness check. |

Use the exact header name `User_Name` (underscore). Service tokens identify trusted callers; Search and Synthesis must derive the user header from their authenticated request context. The Processing token grants access to active document versions without an owner header.
In Swagger UI, use `ProcessingToken` or `DocumentAccessToken` for the corresponding internal endpoints.

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
- `404`: inaccessible resources are indistinguishable from missing resources on user document routes. A repeated deletion also returns `404`.
- `422`: request validation failure, such as invalid UUID/version, missing required fields, invalid status, or an access-check list outside 1–100 entries. FastAPI returns a `detail` array with validation information.
- `503`: required authentication configuration is unavailable. For local user routes, development identity is disabled; for internal routes, the relevant token configuration is missing.
- Unhandled database/storage failures can return `500`; the application does not normalize all failures into the JSON error format or map dependency outages to `503`.

## Database specification

Content uses PostgreSQL 17. With the example configuration, database and user are both `studyhub`; actual values come from `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` in root `.env`.

| Connection / storage | Location |
| --- | --- |
| Host database tools | `127.0.0.1:5433` |
| API, relay, and migration containers | `db:5432` |
| PostgreSQL persistence | Compose volume `postgres-data`, mounted at `/var/lib/postgresql/data` |
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

The document reference is inside JSON; there is no foreign key to `documents`. Relay adds `eventId` and `eventType` to the payload when publishing. `published_at` confirms broker publication, not consumer completion. Published events are currently retained; there is no automatic purge.

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

The relay publishes JSON to the durable topic exchange `document.events`. Its routing key matches `eventType`.

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

## Smoke test

1. In `/docs`, upload a synthetic PDF with `User_Name: alice`. Expect `201` and copy the `documentId`.
2. Use the same ID to fetch metadata. Expect `200` for Alice and `404` for Bob.
3. With `DocumentAccessToken`, send the ID to the batch access route. Expect the ID and version for `User_Name: alice` and an empty list for `bob`.
4. With `ProcessingToken`, fetch version `1` and report `{"status":"succeeded"}`. Expect `200` for the download and `204` for the report. Alice's metadata should now show `succeeded`.
5. Delete the file as Alice. Expect `204`, then retry the worker download and batch access check. Expect `404` for the download and an empty access list. The relay should log publication of the upload and deletion events.

## Current handoff scope

Compose starts PostgreSQL, RabbitMQ, and separate Content API and relay containers, with a one-time migration container. The team-wide Compose setup, Gateway and frontend, document listing, version replacement, sharing, physical file cleanup, and calendar are follow-up work. Access currently uses owner-only rules, and soft-deleted files remain in local storage.
