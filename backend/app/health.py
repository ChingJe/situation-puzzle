from __future__ import annotations

from app.dependencies import get_llm_client, get_storage
from app.models import HealthResponse


def get_health() -> HealthResponse:
    ollama = get_llm_client().health_check()
    storage = get_storage().writable_check()
    status = "ok" if ollama.get("status") == "ok" and storage.get("status") == "ok" else "degraded"
    return HealthResponse(
        status=status,
        backend={"status": "ok"},
        ollama=ollama,
        storage=storage,
    )
