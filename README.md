# StudyHub22 | Content & Metadata Service

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
| `main.py` | FastAPI routes for documents, permission checks, and AI Processing callbacks |
| `relay.py` | Background publisher for the PostgreSQL outbox |
| `migrations/` | PostgreSQL schema migrations, applied in numbered order |
| `setup/` | Setup and startup scripts for Windows and macOS |
| `compose.yaml` | Local PostgreSQL and RabbitMQ services |
| `.env.example` | Local configuration template |
| `requirements.txt` | Python dependencies |

The setup scripts use `.env` and `.venv/` at the repository root. The API creates `uploads/` when a file is uploaded. These local files and directories are excluded from Git.

## Run the Content Service locally

Open Docker Desktop and open a new terminal at the repository root. You need Python 3.12 or 3.13 and Docker Compose. Each developer uses their own `.env` and `.venv`.

### Windows (PowerShell)

Python should be available through `py`.

```powershell
# First-time setup
.\setup\setup-content-service.ps1

# Start the API and relay
.\setup\start-content-service.ps1
```

### macOS (Terminal)

Python should be available through `python3`.

```bash
# First-time setup
bash setup/setup-content-service.sh

# Start the API and relay
bash setup/start-content-service.sh
```

Setup installs dependencies, creates `.env` from `.env.example` if needed, fills missing service tokens, and applies the SQL migrations in order. Existing tokens are preserved. Keep `.env` out of Git and give each calling service only its own matching token.

The startup script brings up PostgreSQL and RabbitMQ, then starts the API and relay. Open the [API docs](http://127.0.0.1:8000/docs), [OpenAPI JSON](http://127.0.0.1:8000/openapi.json), or [RabbitMQ management UI](http://127.0.0.1:15672/). Use your local RabbitMQ credentials from `.env`.

Press **Ctrl+C** to stop the API and relay. Relay logs are in `.venv/relay.log` and `.venv/relay-errors.log`. To stop PostgreSQL and RabbitMQ while preserving their data, run `docker compose stop db rabbitmq`.

## HTTP integration

Use `http://127.0.0.1:8000` when running the API and the caller on the same host. The `/internal/` routes are for service-to-service calls. For local user document routes, set `User_Name` to `alice` or `bob` with `STUDYHUB_DEV_IDENTITY=1`. The internal access-check route uses the same header name and requires a service bearer token.

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

Compose starts PostgreSQL and RabbitMQ. The API and relay run as separate Python processes for local development. The team-wide Compose setup, Gateway and frontend, document listing, version replacement, sharing, physical file cleanup, and calendar are follow-up work. Access currently uses owner-only rules, and soft-deleted files remain in local storage.
