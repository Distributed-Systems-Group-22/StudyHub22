# Content & Metadata Service

Owns original files, metadata, document ownership, soft deletion, and user-visible processing status.

## Run

Run setup and Compose from the repository root; see [the root README](../README.md).
The same Docker image runs three commands:

- API: python -m uvicorn main:app --host 0.0.0.0 --port 8000
- Relay: python -u relay.py
- Migrations: python migrate.py

## Files

| Path | Responsibility |
| --- | --- |
| main.py | HTTP routes, identity checks, document operations |
| relay.py | Publish committed outbox events with broker confirms |
| migrate.py | Serialized, transactional, checksum-tracked migrations |
| migrations/ | Append-only numbered SQL schema changes |
| Dockerfile | Shared API, relay, and migration image |

Document/outbox changes remain in one PostgreSQL transaction. File writes are outside PostgreSQL's atomic guarantees; orphan file reconciliation is follow-up work.

## Contracts

The root README contains the [API specification](../README.md#api-specification-implemented-content-endpoints) and [database specification](../README.md#database-specification), including request/response examples, error semantics, table columns, constraints, and transaction behavior.

See [HTTP contract](../docs/contracts/content-api.md) and [event contract](../docs/contracts/document-events.md).
The API's /openapi.json exposes its machine-readable HTTP schema.

Current scope: owner-only access, version 1 uploads, pending/succeeded/failed processing status, soft deletion, and service-token authorization.
Version replacement, sharing/permission-change events, calendar, physical file cleanup, and Gateway user authentication remain follow-up work.

## Optional host development

From the repository root, create a Python 3.12 environment and install content-service/requirements.txt. Configure environment variables from the root .env (do not commit tokens). The code also supports an untracked content-service/.env for host development.

Use host database port 5433 and RabbitMQ port 5672, and set STUDYHUB_UPLOAD_DIR to the absolute path of the repository-root uploads directory to reuse existing files.

Stop container API/relay before running host copies, start the infrastructure and migration container with Compose, then run uvicorn main:app and python relay.py from this directory.
