
import json
import os
import time
from uuid import UUID

import pika
import psycopg

from app.services.job_execution import process_job


QUEUE_NAME = "synthesis.jobs"


def connect_rabbitmq():
    credentials = pika.PlainCredentials(
        os.environ["RABBITMQ_USER"],
        os.environ["RABBITMQ_PASSWORD"]
    )

    return pika.BlockingConnection(
        pika.ConnectionParameters(
            host=os.getenv("RABBITMQ_HOST", "rabbitmq"),
            port=5672,
            credentials=credentials,
            heartbeat=60,
            blocked_connection_timeout=30
        )
    )


def on_message(channel, method, properties, body):
    try:
        event = json.loads(body)

        if event.get("event_type") != "synthesis.requested":
            raise ValueError("Unsupported event type")

        job_id = UUID(event["job_id"])

    except (ValueError, KeyError, TypeError) as error:
        print(f"Invalid message: {error}", flush=True)

        channel.basic_nack(
            delivery_tag=method.delivery_tag,
            requeue=False
        )
        return

    try:
        process_job(job_id)

        # ACK after database transactions succeed.
        channel.basic_ack(
            delivery_tag=method.delivery_tag
        )

    except Exception as error:
        print(
            f"Worker infrastructure error: {error}",
            flush=True
        )

        # Temporary infrastructure retry policy.
        # Stage 3C-1 test focuses on job execution
        # failures and worker crashes.
        time.sleep(2)

        channel.basic_nack(
            delivery_tag=method.delivery_tag,
            requeue=True
        )


def main():
    while True:
        connection = None

        try:
            connection = connect_rabbitmq()
            channel = connection.channel()

            channel.queue_declare(
                queue=QUEUE_NAME,
                durable=True
            )

            channel.basic_qos(prefetch_count=1)

            channel.basic_consume(
                queue=QUEUE_NAME,
                on_message_callback=on_message,
                auto_ack=False
            )

            print(
                f"Worker consuming queue: {QUEUE_NAME}",
                flush=True
            )

            channel.start_consuming()

        except (pika.exceptions.AMQPError, OSError) as error:
            print(
                f"Worker connection error: {error}",
                flush=True
            )
            time.sleep(5)

        finally:
            if connection is not None and connection.is_open:
                connection.close()


if __name__ == "__main__":
    main()
