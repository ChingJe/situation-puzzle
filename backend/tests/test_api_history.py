from fastapi.testclient import TestClient

from app.config import StorageConfig
from app.dependencies import get_game_service, get_storage
from app.graph.workflow import SituationPuzzleWorkflow
from app.llm.client import FakeLlmClient
from app.main import app
from app.models import SolutionJudgement
from app.services.game_service import GameService
from app.storage import GameStorage


def test_api_history_lists_and_reads_completed_games(tmp_path) -> None:
    storage = GameStorage(StorageConfig(games_dir=str(tmp_path)))
    service = GameService(
        workflow=SituationPuzzleWorkflow(
            FakeLlmClient(solution_judgements=[SolutionJudgement(solved=True)])
        ),
        storage=storage,
    )
    app.dependency_overrides[get_game_service] = lambda: service
    app.dependency_overrides[get_storage] = lambda: storage
    client = TestClient(app)

    game_id = client.post("/api/games", json={"topic": "雨夜"}).json()["game_id"]
    client.post(f"/api/games/{game_id}/solution", json={"solution": "正確答案"})

    history = client.get("/api/history").json()
    detail = client.get(f"/api/history/{game_id}").json()

    assert history["items"][0]["game_id"] == game_id
    assert detail["truth"]
    assert detail["key_facts"]

    app.dependency_overrides.clear()
