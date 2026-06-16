from fastapi.testclient import TestClient

from app.config import StorageConfig
from app.dependencies import get_game_service, get_storage
from app.graph.workflow import SituationPuzzleWorkflow
from app.llm.client import FakeLlmClient
from app.main import app
from app.models import Answer, QuestionJudgement, SolutionJudgement
from app.services.game_service import GameService
from app.storage import GameStorage


def build_client(tmp_path, fake_llm: FakeLlmClient) -> TestClient:
    storage = GameStorage(StorageConfig(games_dir=str(tmp_path)))
    service = GameService(
        workflow=SituationPuzzleWorkflow(fake_llm),
        storage=storage,
    )
    app.dependency_overrides[get_game_service] = lambda: service
    app.dependency_overrides[get_storage] = lambda: storage
    return TestClient(app)


def test_api_game_flow_does_not_leak_hidden_fields(tmp_path) -> None:
    client = build_client(
        tmp_path,
        FakeLlmClient(
            question_judgements=[QuestionJudgement(is_valid_question=True, answer=Answer.YES)],
            solution_judgements=[SolutionJudgement(solved=True)],
        ),
    )

    created = client.post("/api/games", json={"topic": "雨夜"}).json()
    game_id = created["game_id"]
    current = client.get(f"/api/games/{game_id}").json()
    answer = client.post(
        f"/api/games/{game_id}/questions",
        json={"question": "男子還活著嗎？"},
    ).json()
    solved = client.post(
        f"/api/games/{game_id}/solution",
        json={"solution": "正確答案"},
    ).json()

    assert "truth" not in created
    assert "truth" not in current
    assert "key_facts" not in current
    assert answer["display_answer"] == "是"
    assert solved["truth"]

    app.dependency_overrides.clear()


def test_api_invalid_question_uses_unified_error(tmp_path) -> None:
    client = build_client(
        tmp_path,
        FakeLlmClient(
            question_judgements=[QuestionJudgement(is_valid_question=False, answer=None)]
        ),
    )

    game_id = client.post("/api/games", json={"topic": "雨夜"}).json()["game_id"]
    response = client.post(
        f"/api/games/{game_id}/questions",
        json={"question": "提示是什麼？"},
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "INVALID_QUESTION",
            "message": "請輸入可用是／否回答的問題",
        }
    }

    app.dependency_overrides.clear()
