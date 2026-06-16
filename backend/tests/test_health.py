from fastapi.testclient import TestClient

from app.main import app


def test_health_check_returns_backend_status() -> None:
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["backend"]["status"] == "ok"
    assert "llm" in response.json()
    assert "ollama" not in response.json()
