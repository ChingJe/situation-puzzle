from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.graph.workflow import SituationPuzzleWorkflow
from app.llm.client import OllamaLlmClient
from app.services.game_service import GameService
from app.storage import GameStorage


@lru_cache
def get_storage() -> GameStorage:
    return GameStorage(get_settings().storage)


@lru_cache
def get_llm_client() -> OllamaLlmClient:
    return OllamaLlmClient(get_settings())


@lru_cache
def get_game_service() -> GameService:
    return GameService(
        workflow=SituationPuzzleWorkflow(get_llm_client()),
        storage=get_storage(),
    )
