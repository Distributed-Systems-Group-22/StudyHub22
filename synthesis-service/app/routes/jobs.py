
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from fastapi import APIRouter, HTTPException, Header

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
def get_job_status(
    job_id: UUID,
    user_name: str | None = Header(default=None, alias="User_Name")
):
    user_id = user_name or "dev-user-001"

    try:
        with get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        j.job_id,
                        j.status,
                        j.attempts,
                        j.error_message,
                        r.summary_text,
                        r.status AS summary_status
                    FROM synthesis_jobs j
                    LEFT JOIN synthesis_results r ON j.job_id = r.job_id
                    WHERE j.job_id = %s
                      AND j.user_id = %s
                    """,
                    (job_id, user_id)
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
