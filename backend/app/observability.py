from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
import json
import logging
from typing import Any

from app.config import Settings


request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
game_id_var: ContextVar[str | None] = ContextVar("game_id", default=None)
llm_call_id_var: ContextVar[str | None] = ContextVar("llm_call_id", default=None)
raw_logger = logging.getLogger("app.raw_messages")


def get_request_id() -> str | None:
    return request_id_var.get()


def safe_preview(value: str, max_chars: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[:max_chars] + "..."


@contextmanager
def bind_log_context(
    *,
    request_id: str | None = None,
    game_id: str | None = None,
    llm_call_id: str | None = None,
) -> Iterator[None]:
    tokens: list[tuple[ContextVar[str | None], Token[str | None]]] = []
    if request_id is not None:
        tokens.append((request_id_var, request_id_var.set(request_id)))
    if game_id is not None:
        tokens.append((game_id_var, game_id_var.set(game_id)))
    if llm_call_id is not None:
        tokens.append((llm_call_id_var, llm_call_id_var.set(llm_call_id)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    message: str = "",
    **fields: Any,
) -> None:
    logger.log(level, message, extra={"event": event, **fields})


def log_raw_message(
    settings: Settings,
    message_kind: str,
    task: str,
    content: Any,
    *,
    content_type: str = "text",
    game_id: str | None = None,
    llm_call_id: str | None = None,
) -> None:
    mode = settings.logging.raw_message_mode
    if mode == "off":
        return

    content_for_log, content_chars, truncated = _prepare_raw_content(
        content,
        mode=mode,
        max_chars=settings.logging.raw_message_max_chars,
    )
    raw_logger.debug(
        "",
        extra={
            "event": "raw.message",
            "message_kind": message_kind,
            "task": task,
            "mode": mode,
            "content_type": content_type,
            "content": content_for_log,
            "content_chars": content_chars,
            "truncated": truncated,
            **({"game_id": game_id} if game_id else {}),
            **({"llm_call_id": llm_call_id} if llm_call_id else {}),
        },
    )


def _prepare_raw_content(
    content: Any,
    *,
    mode: str,
    max_chars: int,
) -> tuple[Any, int, bool]:
    if isinstance(content, str):
        serialized = content
    else:
        serialized = json.dumps(content, ensure_ascii=False, default=str)

    content_chars = len(serialized)
    limit = max_chars if mode == "full" else min(max_chars, 1000)
    if len(serialized) <= limit:
        return content, content_chars, False

    truncated = serialized[:limit] + "..."
    if isinstance(content, str):
        return truncated, content_chars, True
    return truncated, content_chars, True
