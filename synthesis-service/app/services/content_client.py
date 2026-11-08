import os
import httpx


CONTENT_SERVICE_URL = os.getenv("CONTENT_SERVICE_URL", "http://content-api:8000")
SYNTHESIS_TOKEN = os.getenv("STUDYHUB_SYNTHESIS_TOKEN", "")


def verify_document_access(user_id: str, document_ids: list[str]) -> list[dict]:
    """
    Performs live permission and version checks against the Content Service.
    Implements a Fail-Closed policy: returns an empty list if Content Service
    is unreachable or returns an error.
    """
    if not document_ids:
        return []

    # If running in local standalone test without Content Service configured
    if not SYNTHESIS_TOKEN or not CONTENT_SERVICE_URL:
        print("[ContentClient] STUDYHUB_SYNTHESIS_TOKEN not set; skipping live check.", flush=True)
        return [{"documentId": doc_id, "documentVersion": 1} for doc_id in document_ids]

    url = f"{CONTENT_SERVICE_URL.rstrip('/')}/internal/documents/access-check"
    headers = {
        "Authorization": f"Bearer {SYNTHESIS_TOKEN}",
        "User_Name": user_id,
        "Content-Type": "application/json",
    }
    payload = {"documentIds": document_ids}

    try:
        with httpx.Client(timeout=4.0) as client:
            response = client.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                data = response.json()
                return data.get("documents", [])
            else:
                print(
                    f"[ContentClient] Access check failed with status {response.status_code}: {response.text}",
                    flush=True
                )
                return []
    except Exception as exc:
        print(f"[ContentClient] Access check connection error: {exc}", flush=True)
        return []
