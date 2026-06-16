from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from app.config import ROOT_DIR, StorageConfig
from app.errors import ApiErrorCode, AppError
from app.models import CompletedGameRecord, HistoryItem


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
            raise AppError(ApiErrorCode.STORAGE_ERROR, str(exc), 500) from exc

    def writable_check(self) -> dict[str, object]:
        try:
            self.ensure_ready()
            probe = self.games_dir / ".write-check"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError as exc:
            return {
                "status": "unavailable",
                "games_dir": str(self.games_dir),
                "writable": False,
                "error": str(exc),
            }
        except AppError as exc:
            return {
                "status": "unavailable",
                "games_dir": str(self.games_dir),
                "writable": False,
                "error": exc.message,
            }
        return {"status": "ok", "games_dir": str(self.games_dir), "writable": True}

    def save_completed_game(self, record: CompletedGameRecord) -> None:
        self.ensure_ready()
        target = self.games_dir / f"{record.game_id}.json"
        tmp = target.with_suffix(".json.tmp")
        try:
            tmp.write_text(
                record.model_dump_json(indent=2),
                encoding="utf-8",
            )
            tmp.replace(target)
        except OSError as exc:
            raise AppError(ApiErrorCode.STORAGE_ERROR, str(exc), 500) from exc

    def read_completed_game(self, game_id: str) -> CompletedGameRecord:
        path = self.games_dir / f"{game_id}.json"
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise AppError(ApiErrorCode.GAME_NOT_FOUND, status_code=404) from exc
        except OSError as exc:
            raise AppError(ApiErrorCode.STORAGE_ERROR, str(exc), 500) from exc

        try:
            return CompletedGameRecord.model_validate_json(raw)
        except (ValidationError, json.JSONDecodeError) as exc:
            raise AppError(ApiErrorCode.STORAGE_ERROR, str(exc), 500) from exc

    def list_history(self) -> list[HistoryItem]:
        self.ensure_ready()
        items: list[HistoryItem] = []
        for path in self.games_dir.glob("*.json"):
            try:
                record = CompletedGameRecord.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, ValidationError, json.JSONDecodeError):
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
        return sorted(items, key=lambda item: item.ended_at, reverse=True)
