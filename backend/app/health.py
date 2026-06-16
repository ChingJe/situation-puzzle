from __future__ import annotations

import logging

from app.dependencies import get_llm_client, get_storage
from app.models import HealthResponse
from app.observability import log_event


logger = logging.getLogger("app.health")


def get_health() -> HealthResponse:
    ollama = get_llm_client().health_check()
    storage = get_storage().writable_check()
    status = "ok" if ollama.get("status") == "ok" and storage.get("status") == "ok" else "degraded"
    log_event(
        logger,
        "health.checked",
        level=logging.INFO if status == "ok" else logging.WARNING,
        overall_status=status,
        ollama_status=ollama.get("status"),
        ollama_model=ollama.get("model"),
        ollama_model_available=ollama.get("model_available"),
        storage_status=storage.get("status"),
        storage_writable=storage.get("writable"),
    )
    return HealthResponse(
        status=status,
        backend={"status": "ok"},
        ollama=ollama,
        storage=storage,
    )
