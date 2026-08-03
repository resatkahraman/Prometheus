import hashlib
import json

from app.core.schemas import OrchestrateRequest


CACHE_VERSION = "adam-v0.6.1"


def make_cache_key(request: OrchestrateRequest) -> str:
    payload = {
        "version": CACHE_VERSION,
        "mode": request.mode,
        "provider": request.provider,
        "providers": request.providers,
        "preferred_routes": request.preferred_routes,
        "excluded_routes": request.excluded_routes,
        "task_type_override": request.task_type_override,
        "messages": [
            message.model_dump()
            for message in request.normalized_messages()
        ],
        "system_prompt": request.system_prompt,
        "temperature": request.temperature,
        "max_output_tokens": request.max_output_tokens,
        "include_candidates": request.include_candidates,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
