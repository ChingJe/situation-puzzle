from __future__ import annotations

from datetime import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.config import ROOT_DIR, Settings
from app.observability import game_id_var, llm_call_id_var, request_id_var


TAIPEI = ZoneInfo("Asia/Taipei")

STANDARD_LOG_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, TAIPEI).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
        }
        event = getattr(record, "event", None)
        if event:
            payload["event"] = event
        message = record.getMessage()
        if message:
            payload["message"] = message

        request_id = getattr(record, "request_id", None) or request_id_var.get()
        game_id = getattr(record, "game_id", None) or game_id_var.get()
        llm_call_id = getattr(record, "llm_call_id", None) or llm_call_id_var.get()
        if request_id:
            payload["request_id"] = request_id
        if game_id:
            payload["game_id"] = game_id
        if llm_call_id:
            payload["llm_call_id"] = llm_call_id

        for key, value in record.__dict__.items():
            if key in STANDARD_LOG_ATTRS or key in payload:
                continue
            if key.startswith("_"):
                continue
            payload[key] = _json_safe(value)

        if record.exc_info:
            payload["exception_type"] = record.exc_info[0].__name__
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(settings: Settings) -> None:
    level = getattr(logging, settings.effective_log_level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    for handler in list(root_logger.handlers):
        if getattr(handler, "_situation_puzzle_handler", False):
            root_logger.removeHandler(handler)

    formatter: logging.Formatter
    if settings.logging.format == "json":
        formatter = JsonLogFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )

    if settings.logging.console_enabled:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        console.setLevel(level)
        console._situation_puzzle_handler = True  # type: ignore[attr-defined]
        root_logger.addHandler(console)

    if settings.logging.file_enabled:
        log_dir = _resolve_path(settings.logging.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "app.log",
            maxBytes=settings.logging.max_file_mb * 1024 * 1024,
            backupCount=settings.logging.backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        file_handler._situation_puzzle_handler = True  # type: ignore[attr-defined]
        root_logger.addHandler(file_handler)

    _setup_raw_message_logger(settings, formatter)


def _resolve_path(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT_DIR / candidate
    return candidate


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _setup_raw_message_logger(settings: Settings, formatter: logging.Formatter) -> None:
    raw_logger = logging.getLogger("app.raw_messages")
    raw_logger.setLevel(logging.DEBUG)
    raw_logger.propagate = False
    for handler in list(raw_logger.handlers):
        if getattr(handler, "_situation_puzzle_handler", False):
            raw_logger.removeHandler(handler)

    if settings.logging.raw_message_mode == "off":
        return

    raw_path = _resolve_path(settings.logging.raw_message_log_file)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_handler = RotatingFileHandler(
        raw_path,
        maxBytes=settings.logging.max_file_mb * 1024 * 1024,
        backupCount=settings.logging.backup_count,
        encoding="utf-8",
    )
    raw_handler.setFormatter(formatter)
    raw_handler.setLevel(logging.DEBUG)
    raw_handler._situation_puzzle_handler = True  # type: ignore[attr-defined]
    raw_logger.addHandler(raw_handler)
