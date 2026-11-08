
import os
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from app.services.ai_client import generate_summary
from app.services.mock_documents import get_documents
from app.services.content_client import verify_document_access
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.database import get_connection


MAX_ATTEMPTS = 3
LEASE_SECONDS = 45


def claim_job(job_id):
    """Atomically claim a pending job."""

    token = uuid4()

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT *
                FROM synthesis_jobs
                WHERE job_id = %s
                FOR UPDATE
            """, (job_id,))

            job = cur.fetchone()

            if job is None:
                print(f"Unknown job {job_id}", flush=True)
                return None

            if job["status"] in ("COMPLETED", "FAILED"):
                print(
                    f"Job {job_id} already {job['status']}. Skipping.",
                    flush=True
                )
                return None

            if job["status"] == "RUNNING":
                print(
                    f"Job {job_id} already RUNNING. Skipping.",
                    flush=True
                )
                return None

            now = datetime.now(timezone.utc)

            if job["next_attempt_at"] > now:
                print(
                    f"Job {job_id} not ready yet.",
                    flush=True
                )
                return None

            if job["attempts"] >= MAX_ATTEMPTS:
                cur.execute("""
                    UPDATE synthesis_jobs
                    SET status = 'FAILED',
                        error_message = 'Maximum attempts reached',
                        updated_at = NOW()
                    WHERE job_id = %s
                """, (job_id,))
                return None

            if not job["document_ids"] or not job["instruction"]:
                cur.execute("""
                    UPDATE synthesis_jobs
                    SET status = 'FAILED',
                        error_message = 'Missing job payload',
                        updated_at = NOW()
                    WHERE job_id = %s
                """, (job_id,))
                return None

            lease_until = now + timedelta(
                seconds=LEASE_SECONDS
            )

            cur.execute("""
                UPDATE synthesis_jobs
                SET status = 'RUNNING',
                    attempts = attempts + 1,
                    claim_token = %s,
                    lease_until = %s,
                    updated_at = NOW()
                WHERE job_id = %s
            """, (
                token,
                lease_until,
                job_id
            ))

            return {
                "job_id": job_id,
                "claim_token": token,
                "attempt": job["attempts"] + 1,
                "user_id": job["user_id"],
                "document_ids": job["document_ids"],
                "instruction": job["instruction"],
                "cache_key": job["cache_key"]
            }


def generate_mock_summary(job):
    """Simulate work. Replace with AI in Stage 3C-2."""

    instruction = job["instruction"]
    attempt = job["attempt"]

    print(
        f"Executing job {job['job_id']}, attempt {attempt}",
        flush=True
    )

    # Fault injection for local testing only.
    if "TEST_CRASH_ONCE" in instruction and attempt == 1:
        print("Simulating worker crash!", flush=True)
        os._exit(17)

    if "TEST_FAIL_ONCE" in instruction and attempt == 1:
        raise RuntimeError("Simulated transient AI failure")

    time.sleep(1)

    return (
        "[MOCK SUMMARY - NOT AI GENERATED]\n"
        f"Documents: {', '.join(job['document_ids'])}\n"
        f"Instruction: {instruction}\n"
        f"Completed on attempt {attempt}."
    )


def complete_job(
    job,
    summary_text,
    model_version,
    prompt_version,
    sources=None
):
    """Commit result and completion atomically."""

    summary_id = uuid4()
    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                UPDATE synthesis_jobs
                SET status = 'COMPLETED',
                    completed_at = NOW(),
                    lease_until = NULL,
                    claim_token = NULL,
                    error_message = NULL,
                    updated_at = NOW()
                WHERE job_id = %s
                  AND status = 'RUNNING'
                  AND claim_token = %s
                  AND lease_until > NOW()
                RETURNING job_id
            """, (
                job["job_id"],
                job["claim_token"]
            ))

            if cur.fetchone() is None:
                print(
                    f"Stale completion rejected: {job['job_id']}",
                    flush=True
                )
                return False

            cur.execute("""
                INSERT INTO synthesis_results (
                    summary_id,
                    job_id,
                    cache_key,
                    summary_text,
                    model_version,
                    prompt_version,
                    status
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'VALID')
            """, (
                summary_id,
                job["job_id"],
                job["cache_key"],
                summary_text,
                model_version,
                prompt_version
            ))

            if sources:
                for src in sources:
                    doc_id = src.get("documentId") or src.get("document_id")
                    doc_ver = src.get("documentVersion") or src.get("document_version", 1)
                    cur.execute("""
                        INSERT INTO summary_sources (
                            summary_id,
                            document_id,
                            document_version
                        )
                        VALUES (%s, %s, %s)
                    """, (summary_id, str(doc_id), doc_ver))

    print(
        f"Job {job['job_id']} COMPLETED",
        flush=True
    )
    return True


def fail_job(job, error):
    """Persist a failure and schedule a bounded retry."""

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT status, claim_token, attempts,
                       lease_until
                FROM synthesis_jobs
                WHERE job_id = %s
                FOR UPDATE
            """, (job["job_id"],))

            current = cur.fetchone()

            if (
                current is None
                or current["status"] != "RUNNING"
                or current["claim_token"] != job["claim_token"]
                or current["lease_until"]
                   <= datetime.now(timezone.utc)
            ):
                print(
                    f"Stale failure ignored: {job['job_id']}",
                    flush=True
                )
                return

            if current["attempts"] >= MAX_ATTEMPTS:
                cur.execute("""
                    UPDATE synthesis_jobs
                    SET status = 'FAILED',
                        claim_token = NULL,
                        lease_until = NULL,
                        error_message = %s,
                        updated_at = NOW()
                    WHERE job_id = %s
                """, (str(error)[:500], job["job_id"]))

                print(
                    f"Job {job['job_id']} FAILED permanently",
                    flush=True
                )
                return

            delay = 2 ** current["attempts"]
            retry_at = (
                datetime.now(timezone.utc)
                + timedelta(seconds=delay)
            )

            cur.execute("""
                UPDATE synthesis_jobs
                SET status = 'PENDING',
                    claim_token = NULL,
                    lease_until = NULL,
                    next_attempt_at = %s,
                    error_message = %s,
                    updated_at = NOW()
                WHERE job_id = %s
            """, (
                retry_at,
                str(error)[:500],
                job["job_id"]
            ))

            event_id = uuid4()

            payload = {
                "event_id": str(event_id),
                "event_type": "synthesis.requested",
                "job_id": str(job["job_id"])
            }

            cur.execute("""
                INSERT INTO outbox_events (
                    event_id,
                    event_type,
                    aggregate_id,
                    payload,
                    available_at
                )
                VALUES (%s, %s, %s, %s, %s)
            """, (
                event_id,
                "synthesis.requested",
                job["job_id"],
                Jsonb(payload),
                retry_at
            ))

    print(
        f"Job {job['job_id']} retry scheduled in {delay}s",
        flush=True
    )


def process_job(job_id):
    job = claim_job(job_id)

    if job is None:
        return

    try:
        print(
            f"Executing AI job {job_id}, "
            f"attempt {job['attempt']}",
            flush=True
        )

        # Step 1: Live permission check with Content Service (ADR Live Permission Checks)
        user_id = job.get("user_id", "dev-user-001")
        doc_ids = job["document_ids"]
        verified_docs = verify_document_access(user_id=user_id, document_ids=doc_ids)
        verified_ids = {str(d.get("documentId")) for d in verified_docs}

        # If Content Service token is configured and verification fails, fail closed
        if os.getenv("STUDYHUB_SYNTHESIS_TOKEN") and not all(str(did) in verified_ids for did in doc_ids):
            raise PermissionError(
                f"Access check failed: one or more documents are missing or unauthorized for user {user_id}"
            )

        # Step 2: Get synthetic source documents (or Search Service API in later phase)
        documents = get_documents(
            job["document_ids"]
        )

        # Step 3: Call real Ollama AI.
        result = generate_summary(
            documents=documents,
            instruction=job["instruction"]
        )

        # Step 4: Save result with model metadata and source citations.
        sources = verified_docs if verified_docs else [
            {"documentId": did, "documentVersion": 1} for did in doc_ids
        ]
        completed = complete_job(
            job=job,
            summary_text=result["summary_text"],
            model_version=result["model_version"],
            prompt_version=result["prompt_version"],
            sources=sources
        )

        if completed:
            print(
                f"AI summary saved for job {job_id}",
                flush=True
            )
        else:
            print(
                f"AI result discarded: lease or claim expired "
                f"for job {job_id}",
                flush=True
            )

    except Exception as error:
        print(
            f"AI job {job_id} failed: {error}",
            flush=True
        )

        fail_job(job, error)
