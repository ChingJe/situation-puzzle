from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_storage
from app.models import CompletedGameRecord, HistoryListResponse
from app.storage import GameStorage


router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=HistoryListResponse)
def list_history(storage: GameStorage = Depends(get_storage)) -> HistoryListResponse:
    return HistoryListResponse(items=storage.list_history())


@router.get("/{game_id}", response_model=CompletedGameRecord)
def get_history(
    game_id: str,
    storage: GameStorage = Depends(get_storage),
) -> CompletedGameRecord:
    return storage.read_completed_game(game_id)
