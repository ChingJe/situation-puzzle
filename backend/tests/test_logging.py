import logging

from fastapi.testclient import TestClient

from app.config import StorageConfig
from app.config import Settings
from app.graph.workflow import SituationPuzzleWorkflow
from app.llm.client import FakeLlmClient
from app.logging_config import setup_logging
from app.main import app
from app.models import SolutionJudgement
from app.observability import bind_log_context, log_raw_message
from app.services.game_service import GameService
from app.storage import GameStorage


def test_request_id_header_is_preserved() -> None:
    client = TestClient(app)

    response = client.get("/not-found", headers={"X-Request-ID": "req_test"})

    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "req_test"


def test_game_service_logs_lifecycle_without_hidden_truth(tmp_path, caplog) -> None:
    caplog.set_level(logging.INFO)
    service = GameService(
        workflow=SituationPuzzleWorkflow(
            FakeLlmClient(solution_judgements=[SolutionJudgement(solved=True)])
        ),
        storage=GameStorage(StorageConfig(games_dir=str(tmp_path))),
    )

    created = service.create_game("雨夜、便利商店")
    service.submit_solution(created.game_id, "正確答案")

    events = {getattr(record, "event", None) for record in caplog.records}
    assert "game.create.started" in events
    assert "game.created" in events
    assert "solution.judged" in events
    assert "game.finalized" in events

    serialized_records = "\n".join(
        f"{record.getMessage()} {record.__dict__}" for record in caplog.records
    )
    assert "完整真相" not in serialized_records
    assert "發票暴露時間矛盾" not in serialized_records


def test_raw_message_logger_writes_full_content(tmp_path) -> None:
    raw_path = tmp_path / "messages.log"
    settings = Settings(
        logging={
            "file_enabled": False,
            "console_enabled": False,
            "raw_message_mode": "full",
            "raw_message_log_file": str(raw_path),
            "raw_message_max_chars": 20000,
        }
    )
    setup_logging(settings)

    with bind_log_context(request_id="req_raw", llm_call_id="llm_raw"):
        log_raw_message(
            settings,
            "llm.parsed_output",
            "generate_puzzle",
            {"truth": "完整真相可以被 raw message 保存"},
            content_type="json",
        )

    raw_log = raw_path.read_text(encoding="utf-8")
    assert '"event": "raw.message"' in raw_log
    assert '"request_id": "req_raw"' in raw_log
    assert "完整真相可以被 raw message 保存" in raw_log
