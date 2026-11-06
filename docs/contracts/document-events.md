# Document event contract

## RabbitMQ integration

The relay publishes JSON to the durable topic exchange `document.events`. Its routing key matches `eventType`.

| Event | Queue | Consumer | Expected action |
| --- | --- | --- | --- |
| `document.uploaded` | `document.jobs` | AI Processing | Fetch the file using the ID and version, process it, and report the final result. |
| `document.deleted` | `search.document-events` | Search & Index | Remove or invalidate the document's index entries. |
| `document.deleted` | `synthesis.document-events` | Synthesis | Invalidate cached results derived from the document. |

```json
{
  "eventId": "1fc17bd4-9a02-4d10-a168-562bd3fd1b24",
  "eventType": "document.uploaded",
  "documentId": "04a1dc78-a5d7-428a-8773-3ba9ec503c22",
  "documentVersion": 1
}
```

The relay can resend an event with the same `eventId`, so consumers should handle duplicates. The AI worker should stop processing that ID and version if fetching the file returns `404`. A soft deletion takes effect in Content as soon as its database transaction commits. The deletion event then lets downstream services clean up their own data.


Delivery is at least once. Global or per-document ordering is not guaranteed with multiple relays. Permission-change and version-replacement events are not implemented yet; agree their contracts before adding producers.
