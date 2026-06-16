from __future__ import annotations

import logging

from app.dependencies import get_llm_client, get_storage
from app.models import HealthResponse
from app.observability import log_event


logger = logging.getLogger("app.health")


def get_health() -> HealthResponse:
    llm = get_llm_client().health_check()
    storage = get_storage().writable_check()
    status = "ok" if llm.get("status") == "ok" and storage.get("status") == "ok" else "degraded"
    log_event(
        logger,
        "health.checked",
        level=logging.INFO if status == "ok" else logging.WARNING,
        overall_status=status,
        llm_provider=llm.get("provider"),
        llm_status=llm.get("status"),
        llm_model=llm.get("model"),
        llm_model_available=llm.get("model_available"),
        storage_status=storage.get("status"),
        storage_writable=storage.get("writable"),
    )
    return HealthResponse(
        status=status,
        backend={"status": "ok"},
        llm=llm,
        storage=storage,
    )
