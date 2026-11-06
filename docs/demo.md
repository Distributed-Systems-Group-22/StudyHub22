# Integration and failure checks

Run these checks with synthetic files after starting Compose. These are a manual verification checklist, not recorded test results.

1. Upload as Alice in /docs. Confirm metadata is visible to Alice but returns 404 for Bob.
2. Fetch the original file with the Processing token. Report succeeded twice; both requests should return 204. A subsequent failed report should return 409.
3. Use Search/Synthesis token and Alice's identity to batch-check the document. Delete it, then confirm the access check is empty and worker download returns 404.
4. Stop RabbitMQ: docker compose stop rabbitmq. Upload another file; API should still return 201. Restart with docker compose start rabbitmq and confirm relay publishes the pending event.
5. Recreate API: docker compose up -d --force-recreate content-api. Confirm an undeleted document remains downloadable.
6. Restart the stack and inspect content-migrate logs: previously recorded migrations should not be applied again.
7. Simulate duplicate delivery at the consumer when the other services are integrated. Consumers must deduplicate eventId and reject unavailable/stale versions.
8. Stop Content when Search/Synthesis are integrated. Both should withhold unverified content (fail closed).

A relay success log proves broker publication, not successful downstream processing. Queue depth and consumer results must be checked separately.
