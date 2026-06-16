from __future__ import annotations

import json
import logging
from pathlib import Path
from time import perf_counter

from pydantic import ValidationError

from app.config import ROOT_DIR, StorageConfig
from app.errors import ApiErrorCode, AppError
from app.models import CompletedGameRecord, HistoryItem
from app.observability import log_event


logger = logging.getLogger("app.storage")


class GameStorage:
    def __init__(self, config: StorageConfig) -> None:
        self.games_dir = self._resolve_path(config.games_dir)

    @staticmethod
    def _resolve_path(path: str) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = ROOT_DIR / candidate
        return candidate

    def ensure_ready(self) -> None:
        try:
            self.games_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            log_event(
                logger,
                "storage.failed",
                level=logging.ERROR,
                path=self._display_path(self.games_dir),
                exception_type=type(exc).__name__,
                message=str(exc),
            )
            raise AppError(ApiErrorCode.STORAGE_ERROR, str(exc), 500) from exc
        log_event(
            logger,
            "storage.ensure_ready",
            path=self._display_path(self.games_dir),
        )

    def writable_check(self) -> dict[str, object]:
        try:
            self.ensure_ready()
            probe = self.games_dir / ".write-check"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError as exc:
            log_event(
                logger,
                "storage.writable_check.failed",
                level=logging.WARNING,
                path=self._display_path(self.games_dir),
                exception_type=type(exc).__name__,
                message=str(exc),
            )
            return {
                "status": "unavailable",
                "games_dir": str(self.games_dir),
                "writable": False,
                "error": str(exc),
            }
        except AppError as exc:
            log_event(
                logger,
                "storage.writable_check.failed",
                level=logging.WARNING,
                path=self._display_path(self.games_dir),
                error_code=exc.code.value,
                message=exc.message,
            )
            return {
                "status": "unavailable",
                "games_dir": str(self.games_dir),
                "writable": False,
                "error": exc.message,
            }
        log_event(
            logger,
            "storage.writable_check.finished",
            path=self._display_path(self.games_dir),
            writable=True,
        )
        return {"status": "ok", "games_dir": str(self.games_dir), "writable": True}

    def save_completed_game(self, record: CompletedGameRecord) -> None:
        self.ensure_ready()
        start = perf_counter()
        target = self.games_dir / f"{record.game_id}.json"
        tmp = target.with_suffix(".json.tmp")
        log_event(
            logger,
            "storage.write.started",
            game_id=record.game_id,
            path=self._display_path(target),
        )
        try:
            tmp.write_text(
                record.model_dump_json(indent=2),
                encoding="utf-8",
            )
            tmp.replace(target)
        except OSError as exc:
            log_event(
                logger,
                "storage.failed",
                level=logging.ERROR,
                game_id=record.game_id,
                path=self._display_path(target),
                exception_type=type(exc).__name__,
                message=str(exc),
                duration_ms=round((perf_counter() - start) * 1000, 2),
            )
            raise AppError(ApiErrorCode.STORAGE_ERROR, str(exc), 500) from exc
        log_event(
            logger,
            "storage.write.finished",
            game_id=record.game_id,
            path=self._display_path(target),
            duration_ms=round((perf_counter() - start) * 1000, 2),
        )

    def read_completed_game(self, game_id: str) -> CompletedGameRecord:
        start = perf_counter()
        path = self.games_dir / f"{game_id}.json"
        log_event(
            logger,
            "storage.read.started",
            game_id=game_id,
            path=self._display_path(path),
        )
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            log_event(
                logger,
                "storage.failed",
                level=logging.WARNING,
                game_id=game_id,
                path=self._display_path(path),
                error_code=ApiErrorCode.GAME_NOT_FOUND.value,
                duration_ms=round((perf_counter() - start) * 1000, 2),
            )
            raise AppError(ApiErrorCode.GAME_NOT_FOUND, status_code=404) from exc
        except OSError as exc:
            log_event(
                logger,
                "storage.failed",
                level=logging.ERROR,
                game_id=game_id,
                path=self._display_path(path),
                exception_type=type(exc).__name__,
                message=str(exc),
                duration_ms=round((perf_counter() - start) * 1000, 2),
            )
            raise AppError(ApiErrorCode.STORAGE_ERROR, str(exc), 500) from exc

        try:
            record = CompletedGameRecord.model_validate_json(raw)
        except (ValidationError, json.JSONDecodeError) as exc:
            log_event(
                logger,
                "storage.failed",
                level=logging.ERROR,
                game_id=game_id,
                path=self._display_path(path),
                exception_type=type(exc).__name__,
                message=str(exc),
                duration_ms=round((perf_counter() - start) * 1000, 2),
            )
            raise AppError(ApiErrorCode.STORAGE_ERROR, str(exc), 500) from exc
        log_event(
            logger,
            "storage.read.finished",
            game_id=game_id,
            path=self._display_path(path),
            duration_ms=round((perf_counter() - start) * 1000, 2),
        )
        return record

    def list_history(self) -> list[HistoryItem]:
        start = perf_counter()
        self.ensure_ready()
        items: list[HistoryItem] = []
        for path in self.games_dir.glob("*.json"):
            try:
                record = CompletedGameRecord.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, ValidationError, json.JSONDecodeError) as exc:
                log_event(
                    logger,
                    "storage.corrupt_file_skipped",
                    level=logging.WARNING,
                    path=self._display_path(path),
                    exception_type=type(exc).__name__,
                    message=str(exc),
                )
                continue
            items.append(
                HistoryItem(
                    game_id=record.game_id,
                    title=record.title,
                    topic=record.topic,
                    status=record.status,
                    question_count=len(record.questions),
                    created_at=record.created_at,
                    ended_at=record.ended_at,
                )
            )
        sorted_items = sorted(items, key=lambda item: item.ended_at, reverse=True)
        log_event(
            logger,
            "storage.history_list.finished",
            path=self._display_path(self.games_dir),
            record_count=len(sorted_items),
            duration_ms=round((perf_counter() - start) * 1000, 2),
        )
        return sorted_items

    @staticmethod
    def _display_path(path: Path) -> str:
        try:
            return str(path.relative_to(ROOT_DIR))
        except ValueError:
            return str(path)
