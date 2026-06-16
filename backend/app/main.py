from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings


settings = get_settings()

app = FastAPI(title="Situation Puzzle API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check() -> dict[str, object]:
    return {
        "status": "ok",
        "backend": {"status": "ok"},
        "ollama": {
            "status": "unchecked",
            "base_url": settings.ollama_base_url,
            "model": settings.ollama_model,
            "model_available": None,
        },
        "storage": {
            "status": "ok",
            "games_dir": settings.storage.games_dir,
            "writable": None,
        },
    }

