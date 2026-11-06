
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.database import get_connection
from app.services.job_execution import MAX_ATTEMPTS


POLL_INTERVAL = 2


def recover_expired_jobs():
    recovered = 0

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:

            cur.execute("""
                SELECT job_id, attempts
                FROM synthesis_jobs
                WHERE status = 'RUNNING'
                  AND lease_until <= NOW()
                ORDER BY lease_until
                LIMIT 20
                FOR UPDATE SKIP LOCKED
            """)

            jobs = cur.fetchall()

            for job in jobs:
                job_id = job["job_id"]
                attempts = job["attempts"]

                if attempts >= MAX_ATTEMPTS:
                    cur.execute("""
                        UPDATE synthesis_jobs
                        SET status = 'FAILED',
                            claim_token = NULL,
                            lease_until = NULL,
                            error_message = 'Lease expired; max attempts reached',
                            updated_at = NOW()
                        WHERE job_id = %s
                    """, (job_id,))

                    print(
                        f"Expired job {job_id} FAILED",
                        flush=True
                    )
                    continue

                delay = 2 ** attempts

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
                        error_message = 'Worker lease expired',
                        updated_at = NOW()
                    WHERE job_id = %s
                """, (retry_at, job_id))

                event_id = uuid4()

                payload = {
                    "event_id": str(event_id),
                    "event_type": "synthesis.requested",
                    "job_id": str(job_id)
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
                    job_id,
                    Jsonb(payload),
                    retry_at
                ))

                recovered += 1

                print(
                    f"Recovered job {job_id}; "
                    f"retry in {delay}s",
                    flush=True
                )

    return recovered


def main():
    print("Recovery Service started", flush=True)

    while True:
        try:
            recover_expired_jobs()

        except (psycopg.Error, OSError) as error:
            print(
                f"Recovery error: {error}",
                flush=True
            )

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
