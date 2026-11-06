
import hashlib
import json


MODEL_VERSION = "mock-model-v1"
PROMPT_VERSION = "prompt-v1"
RETRIEVAL_VERSION = "retrieval-v1"


def generate_cache_key(
    user_id: str,
    document_ids: list[str],
    instruction: str
) -> str:
    payload = {
        "user_id": user_id,
        "documents": sorted(document_ids),
        "instruction": instruction.strip(),
        "model_version": MODEL_VERSION,
        "prompt_version": PROMPT_VERSION,
        "retrieval_version": RETRIEVAL_VERSION
    }

    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()
