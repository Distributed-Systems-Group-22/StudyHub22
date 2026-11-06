
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from fastapi import APIRouter, HTTPException

from app.database import get_connection
from app.schemas import JobStatusResponse


router = APIRouter(
    prefix="/api/v1/summaries/jobs",
    tags=["Jobs"]
)


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse
)
def get_job_status(job_id: UUID):

    try:
        with get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        job_id,
                        status,
                        attempts,
                        error_message
                    FROM synthesis_jobs
                    WHERE job_id = %s
                      AND user_id = %s
                    """,
                    (job_id, "dev-user-001")
                )

                job = cur.fetchone()

        if job is None:
            raise HTTPException(
                status_code=404,
                detail="Job not found"
            )

        return JobStatusResponse(**job)

    except psycopg.Error:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable"
        )
