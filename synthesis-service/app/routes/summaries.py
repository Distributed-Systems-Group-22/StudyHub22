
import json
from uuid import uuid4

import psycopg
from fastapi import APIRouter, HTTPException, status, Header
from psycopg.types.json import Jsonb

from app.database import get_connection
from app.schemas import SummaryRequest, SummaryJobResponse
from app.services.cache import generate_cache_key


router = APIRouter(
    prefix="/api/v1/summaries",
    tags=["Summaries"]
)

# Development fallback.
DEV_USER_ID = "dev-user-001"


@router.post(
    "",
    response_model=SummaryJobResponse,
    status_code=status.HTTP_202_ACCEPTED
)
def create_summary(
    request: SummaryRequest,
    user_name: str | None = Header(default=None, alias="User_Name")
):

    user_id = user_name or DEV_USER_ID
    job_id = uuid4()
    event_id = uuid4()

    cache_key = generate_cache_key(
        user_id=user_id,
        document_ids=request.document_ids,
        instruction=request.instruction
    )

    event_payload = {
        "event_id": str(event_id),
        "event_type": "synthesis.requested",
        "job_id": str(job_id),
        "user_id": user_id,
        "document_ids": request.document_ids,
        "instruction": request.instruction,
        "cache_key": cache_key
    }

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:

                # 1. Save the complete job
                cur.execute(
                    """
                    INSERT INTO synthesis_jobs (
                        job_id,
                        user_id,
                        cache_key,
                        document_ids,
                        instruction,
                        status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        job_id,
                        user_id,
                        cache_key,
                        Jsonb(request.document_ids),
                        request.instruction,
                        "PENDING"
                    )
                )

                # 2. Save the outbox event
                # Both inserts are in the same transaction.
                cur.execute(
                    """
                    INSERT INTO outbox_events (
                        event_id,
                        event_type,
                        aggregate_id,
                        payload
                    )
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        event_id,
                        "synthesis.requested",
                        job_id,
                        Jsonb(event_payload)
                    )
                )

        return SummaryJobResponse(
            job_id=job_id,
            status="PENDING",
            cache_hit=False
        )

    except psycopg.Error:
        raise HTTPException(
            status_code=503,
            detail="Unable to create summary job"
        )
