
import json
import os
import time

import pika
import psycopg
from psycopg.rows import dict_row

from app.database import get_connection


QUEUE_NAME = "synthesis.jobs"
POLL_INTERVAL = 2


def connect_rabbitmq():
    credentials = pika.PlainCredentials(
        os.environ["RABBITMQ_USER"],
        os.environ["RABBITMQ_PASSWORD"]
    )

    parameters = pika.ConnectionParameters(
        host=os.getenv("RABBITMQ_HOST", "rabbitmq"),
        port=5672,
        credentials=credentials,
        heartbeat=60,
        blocked_connection_timeout=30
    )

    return pika.BlockingConnection(parameters)


def publish_one(channel):
    # One transaction protects the outbox row
    # while publishing and marking it as sent.
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT event_id, event_type, payload
                FROM outbox_events
                WHERE published_at IS NULL
                AND available_at <= NOW()
                ORDER BY available_at, created_at, event_id
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            """)

            event = cur.fetchone()

            if event is None:
                return False

            if event["event_type"] != "synthesis.requested":
                raise ValueError(
                    f"Unsupported event: {event['event_type']}"
                )

            body = json.dumps(
                event["payload"]
            ).encode("utf-8")

            channel.basic_publish(
                exchange="",
                routing_key=QUEUE_NAME,
                body=body,
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type="application/json",
                    message_id=str(event["event_id"])
                ),
                mandatory=True
            )

            # Only reached after broker confirmation.
            cur.execute("""
                UPDATE outbox_events
                SET published_at = NOW(),
                    attempts = attempts + 1
                WHERE event_id = %s
            """, (event["event_id"],))

            print(
                f"Published event {event['event_id']}",
                flush=True
            )

    return True


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

            # Publisher confirms
            channel.confirm_delivery()

            print(
                "Outbox Relay connected to RabbitMQ",
                flush=True
            )

            while True:
                published = publish_one(channel)

                if not published:
                    # Keep connection heartbeats alive
                    connection.process_data_events(
                        time_limit=POLL_INTERVAL
                    )

        except (
            pika.exceptions.AMQPError,
            psycopg.Error,
            OSError,
            ValueError
        ) as error:
            print(
                f"Outbox Relay error: {error}",
                flush=True
            )
            time.sleep(5)

        finally:
            if connection is not None and connection.is_open:
                connection.close()


if __name__ == "__main__":
    main()
