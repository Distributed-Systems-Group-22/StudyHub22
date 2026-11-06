
# Synthetic documents for local integration testing.
# No real user content is used.

MOCK_DOCUMENTS = {
    "doc-601": {
        "title": "Microservices Architecture",
        "version": 1,
        "content": """
Microservices divide an application into independently
deployable services.

Each service is responsible for a specific business
capability and owns its data.

Services communicate through synchronous APIs or
asynchronous messages.

Benefits include independent deployment, fault
isolation and scalability.

Challenges include network failures, distributed
transactions and data consistency.
"""
    },

    "doc-602": {
        "title": "Message Queues and Resilience",
        "version": 1,
        "content": """
Message queues support asynchronous communication
between distributed services.

RabbitMQ allows producers to publish messages while
consumers process them independently.

Acknowledgements help avoid message loss when a
consumer crashes.

Idempotent consumers prevent duplicate messages
from creating duplicate effects.

Retry with backoff reduces pressure during temporary
failures.

Transactional outbox prevents database commits from
being disconnected from message publication.

Circuit breakers help prevent repeated calls to
unavailable downstream services.
"""
    }
}


def get_documents(document_ids):
    documents = []

    for document_id in document_ids:
        if document_id not in MOCK_DOCUMENTS:
            raise ValueError(
                f"Mock document not found: {document_id}"
            )

        documents.append({
            "document_id": document_id,
            **MOCK_DOCUMENTS[document_id]
        })

    return documents
