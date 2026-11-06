import json
import os
import time

import pika
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
from pathlib import Path


load_dotenv(Path(__file__).resolve().with_name(".env"))
DATABASE_URL = os.environ["STUDYHUB_DATABASE_URL"]
AMQP_URL = os.environ["STUDYHUB_AMQP_URL"]
EXCHANGE = "document.events"


def publish_next_event(channel):
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        event = conn.execute(
            """
            SELECT event_id, event_type, payload
            FROM outbox_events
            WHERE published_at IS NULL
            ORDER BY created_at, event_id
            LIMIT 1
            FOR UPDATE SKIP LOCKED
            """
        ).fetchone()

        if event is None:
            return False

        event_id = str(event["event_id"])
        message = {
            "eventId": event_id,
            "eventType": event["event_type"],
            **event["payload"],
        }

        channel.basic_publish(
            exchange=EXCHANGE,
            routing_key=event["event_type"],
            body=json.dumps(message).encode("utf-8"),
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,
                message_id=event_id,
            ),
            mandatory=True,
        )

        conn.execute(
            "UPDATE outbox_events SET published_at = NOW() WHERE event_id = %s",
            (event["event_id"],),
        )

    print(f"Published {event_id}", flush=True)
    return True


def run_relay():
    parameters = pika.URLParameters(AMQP_URL)
    parameters.blocked_connection_timeout = 10

    while True:
        try:
            with pika.BlockingConnection(parameters) as connection:
                channel = connection.channel()
                channel.exchange_declare(
                    exchange=EXCHANGE, exchange_type="topic", durable=True
                )

                queue_bindings = [
                    ("document.jobs", "document.uploaded"),
                    ("search.document-events", "document.deleted"),
                    ("synthesis.document-events", "document.deleted"),
                ]

                for queue_name, routing_key in queue_bindings:
                    channel.queue_declare(queue=queue_name, durable=True)
                    channel.queue_bind(
                        queue=queue_name,
                        exchange=EXCHANGE,
                        routing_key=routing_key,
                    )

                channel.confirm_delivery()
                print("Relay ready", flush=True)

                while True:
                    if not publish_next_event(channel):
                        connection.sleep(1)

        except (pika.exceptions.AMQPError, psycopg.Error) as error:
            print(f"Relay retrying in 3 seconds: {error}", flush=True)
            time.sleep(3)


if __name__ == "__main__":
    run_relay()