from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import StorageConfig
from app.models import (
    Answer,
    CompletedGameRecord,
    Difficulty,
    GameStatus,
    QuestionRecord,
    SolutionAttempt,
)
from app.storage import GameStorage


def make_record(game_id: str, ended_at: datetime) -> CompletedGameRecord:
    created_at = ended_at - timedelta(minutes=10)
    return CompletedGameRecord(
        game_id=game_id,
        topic="主題",
        title=f"標題 {game_id}",
        surface_story="謎面",
        truth="完整真相",
        key_facts=["關鍵一"],
        forbidden_assumptions=[],
        difficulty=Difficulty.MEDIUM,
        questions=[
            QuestionRecord(
                question="是嗎？",
                answer=Answer.YES,
                created_at=created_at,
            )
        ],
        solution_attempts=[
            SolutionAttempt(solution="答案", solved=True, created_at=ended_at)
        ],
        status=GameStatus.SOLVED,
        created_at=created_at,
        ended_at=ended_at,
    )


def test_storage_writes_reads_and_lists_history(tmp_path) -> None:
    storage = GameStorage(StorageConfig(games_dir=str(tmp_path)))
    older = make_record("older", datetime(2026, 6, 16, 10, tzinfo=ZoneInfo("Asia/Taipei")))
    newer = make_record("newer", datetime(2026, 6, 16, 11, tzinfo=ZoneInfo("Asia/Taipei")))

    storage.save_completed_game(older)
    storage.save_completed_game(newer)

    assert storage.read_completed_game("older").title == "標題 older"
    assert [item.game_id for item in storage.list_history()] == ["newer", "older"]


def test_storage_skips_corrupt_json_in_history(tmp_path) -> None:
    storage = GameStorage(StorageConfig(games_dir=str(tmp_path)))
    record = make_record("ok", datetime(2026, 6, 16, 11, tzinfo=ZoneInfo("Asia/Taipei")))
    storage.save_completed_game(record)
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")

    items = storage.list_history()

    assert len(items) == 1
    assert items[0].game_id == "ok"
