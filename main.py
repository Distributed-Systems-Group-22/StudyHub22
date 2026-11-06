import os
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Response, UploadFile
from psycopg.rows import dict_row
from pydantic import BaseModel, Field
from psycopg.types.json import Jsonb
from secrets import compare_digest

from fastapi import Path as ApiPath
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import Literal
from dotenv import load_dotenv

app = FastAPI(title="StudyHub Content Service")

load_dotenv(Path(__file__).resolve().with_name(".env"))
DATABASE_URL = os.environ["STUDYHUB_DATABASE_URL"]
UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"
MAX_FILE_SIZE = 5 * 1024 * 1024

class BatchAccessRequest(BaseModel):
    documentIds: list[UUID] = Field(min_length=1, max_length=100)


class ReadableDocument(BaseModel):
    documentId: UUID
    documentVersion: int


class BatchAccessResponse(BaseModel):
    documents: list[ReadableDocument]

def get_current_user(
    user_name: str | None = Header(default=None, alias="User_Name"),
) -> str:
    if os.getenv("STUDYHUB_DEV_IDENTITY") != "1":
        raise HTTPException(status_code=503, detail="Identity is not configured.")

    if user_name is None or user_name not in ("alice", "bob"):
        raise HTTPException(status_code=401, detail="Use alice or bob for local testing.")

    return user_name

processing_bearer = HTTPBearer(scheme_name="ProcessingToken", auto_error=False)


def require_processing_service(
    credentials: HTTPAuthorizationCredentials | None = Depends(processing_bearer),
) -> None:
    expected_token = os.getenv("STUDYHUB_PROCESSING_TOKEN")

    if not expected_token:
        raise HTTPException(status_code=503, detail="Processing token is not configured.")

    if credentials is None or not compare_digest(
        credentials.credentials.encode("utf-8"),
        expected_token.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid processing token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


document_access_bearer = HTTPBearer(
    scheme_name="DocumentAccessToken",
    auto_error=False,
)


def get_document_access_user(
    user_name: str = Header(alias="User_Name", min_length=1, max_length=128),
    credentials: HTTPAuthorizationCredentials | None = Depends(document_access_bearer),
) -> str:
    configured_tokens = [
        token
        for token in (
            os.getenv("STUDYHUB_SEARCH_TOKEN"),
            os.getenv("STUDYHUB_SYNTHESIS_TOKEN"),
        )
        if token
    ]

    if not configured_tokens:
        raise HTTPException(
            status_code=503,
            detail="Document access tokens are not configured.",
        )

    if credentials is None or not any(
        compare_digest(credentials.credentials.encode("utf-8"), token.encode("utf-8"))
        for token in configured_tokens
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid document access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user_name

    
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/documents", status_code=201)
def upload_document(
    file: UploadFile,
    current_user: str = Depends(get_current_user),
):
    contents = file.file.read(MAX_FILE_SIZE + 1)

    if not contents:
        raise HTTPException(status_code=400, detail="The file is empty.")
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="The file exceeds 5 MiB.")
    if not file.filename:
        raise HTTPException(status_code=400, detail="A filename is required.")

    document_id = uuid4()
    size_bytes = len(contents)

    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        document = conn.execute(
            """
            INSERT INTO documents (id, original_filename, size_bytes, owner_id)
            VALUES (%s, %s, %s, %s)
            RETURNING version
            """,
            (document_id, file.filename, size_bytes, current_user),
        ).fetchone()

        UPLOAD_DIR.mkdir(exist_ok=True)
        (UPLOAD_DIR / str(document_id)).write_bytes(contents)

        payload = {
            "documentId": str(document_id),
            "documentVersion": document["version"],
        }

        conn.execute(
            """
            INSERT INTO outbox_events (event_id, event_type, payload)
            VALUES (%s, %s, %s)
            """,
            (uuid4(), "document.uploaded", Jsonb(payload)),
        )
        
    return {
        "documentId": str(document_id),
        "originalFilename": file.filename,
        "sizeBytes": size_bytes,
    }


@app.get("/documents/{document_id}")
def get_document(
    document_id: UUID,
    current_user: str = Depends(get_current_user),
):
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        document = conn.execute(
            """
            SELECT id AS "documentId",
                original_filename AS "originalFilename",
                size_bytes AS "sizeBytes",
                version AS "documentVersion",
                processing_status AS "processingStatus"
            FROM documents
            WHERE id = %s AND owner_id = %s AND deleted_at IS NULL
            """,
            (document_id, current_user),
        ).fetchone()

    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    return document


@app.post(
    "/internal/documents/access-check",
    response_model=BatchAccessResponse,
    responses={
        401: {"description": "Missing or invalid document access token"},
        503: {"description": "Document access tokens are not configured"},
    },
)
def check_document_access(
    request: BatchAccessRequest,
    current_user: str = Depends(get_document_access_user),
):
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        documents = conn.execute(
            """
            SELECT id AS "documentId",
                   version AS "documentVersion"
            FROM documents
            WHERE owner_id = %s AND id = ANY(%s) AND deleted_at IS NULL
            """,
            (current_user, request.documentIds),
        ).fetchall()

    return {"documents": documents}


@app.delete("/documents/{document_id}", status_code=204, response_class=Response)
def delete_document(
    document_id: UUID,
    current_user: str = Depends(get_current_user),
):
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        deleted_document = conn.execute(
            """
            UPDATE documents
            SET deleted_at = CURRENT_TIMESTAMP
            WHERE id = %s
              AND owner_id = %s
              AND deleted_at IS NULL
            RETURNING id, version
            """,
            (document_id, current_user),
        ).fetchone()

        if deleted_document is None:
            raise HTTPException(status_code=404, detail="Document not found.")

        payload = {
            "documentId": str(deleted_document["id"]),
            "documentVersion": deleted_document["version"],
        }

        conn.execute(
            """
            INSERT INTO outbox_events (event_id, event_type, payload)
            VALUES (%s, %s, %s)
            """,
            (uuid4(), "document.deleted", Jsonb(payload)),
        )

    return Response(status_code=204)

@app.get(
    "/internal/documents/{document_id}/versions/{document_version}/file",
    dependencies=[Depends(require_processing_service)],
    response_class=FileResponse,
    responses={
        200: {
            "description": "Original file bytes",
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
        },
        401: {"description": "Missing or invalid processing token"},
        404: {"description": "Document deleted, missing, or version no longer current"},
        500: {"description": "File missing from storage"},
        503: {"description": "Processing token is not configured"},
    },
)
def get_processing_file(
    document_id: UUID,
    document_version: int = ApiPath(ge=1),
):
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        document = conn.execute(
            """
            SELECT original_filename
            FROM documents
            WHERE id = %s
              AND version = %s
              AND deleted_at IS NULL
            """,
            (document_id, document_version),
        ).fetchone()

    if document is None:
        raise HTTPException(status_code=404, detail="Document version not available.")

    storage_path = UPLOAD_DIR / str(document_id)
    if not storage_path.is_file():
        raise HTTPException(status_code=500, detail="File missing from storage.")

    return FileResponse(
        storage_path,
        media_type="application/octet-stream",
        filename=document["original_filename"],
    )


class ProcessingStatusRequest(BaseModel):
    status: Literal["succeeded", "failed"]


@app.put(
    "/internal/documents/{document_id}/versions/{document_version}/processing-status",
    dependencies=[Depends(require_processing_service)],
    status_code=204,
    response_class=Response,
    responses={
        401: {"description": "Missing or invalid processing token"},
        404: {"description": "Document deleted, missing, or version no longer current"},
        409: {"description": "A different final status is already recorded"},
        503: {"description": "Processing token is not configured"},
    },
)
def update_processing_status(
    document_id: UUID,
    request: ProcessingStatusRequest,
    document_version: int = ApiPath(ge=1),
):
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        document = conn.execute(
            """
            SELECT processing_status
            FROM documents
            WHERE id = %s
              AND version = %s
              AND deleted_at IS NULL
            FOR UPDATE
            """,
            (document_id, document_version),
        ).fetchone()

        if document is None:
            raise HTTPException(status_code=404, detail="Document version not available.")

        current_status = document["processing_status"]

        if current_status == "pending":
            conn.execute(
                "UPDATE documents SET processing_status = %s WHERE id = %s",
                (request.status, document_id),
            )
        elif current_status != request.status:
            raise HTTPException(
                status_code=409,
                detail="A different final status is already recorded.",
            )

    return Response(status_code=204)