# Content HTTP contract

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


Container callers use http://content-api:8000. User_Name must come from authenticated caller context. Gateway authentication is not implemented here.
