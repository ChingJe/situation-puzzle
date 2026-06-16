from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_game_service
from app.models import (
    AbandonGameResponse,
    AskQuestionRequest,
    AskQuestionResponse,
    CreateGameRequest,
    CreateGameResponse,
    PublicGameResponse,
    SubmitSolutionRequest,
    SubmitSolutionResponse,
)
from app.services.game_service import GameService


router = APIRouter(prefix="/api/games", tags=["games"])


@router.post("", response_model=CreateGameResponse)
def create_game(
    request: CreateGameRequest,
    service: GameService = Depends(get_game_service),
) -> CreateGameResponse:
    return service.create_game(request.topic)


@router.get("/{game_id}", response_model=PublicGameResponse, response_model_exclude_none=True)
def get_game(
    game_id: str,
    service: GameService = Depends(get_game_service),
) -> PublicGameResponse:
    return service.get_game(game_id)


@router.post("/{game_id}/questions", response_model=AskQuestionResponse)
def ask_question(
    game_id: str,
    request: AskQuestionRequest,
    service: GameService = Depends(get_game_service),
) -> AskQuestionResponse:
    return service.ask_question(game_id, request.question)


@router.post(
    "/{game_id}/solution",
    response_model=SubmitSolutionResponse,
    response_model_exclude_none=True,
)
def submit_solution(
    game_id: str,
    request: SubmitSolutionRequest,
    service: GameService = Depends(get_game_service),
) -> SubmitSolutionResponse:
    return service.submit_solution(game_id, request.solution)


@router.post("/{game_id}/abandon", response_model=AbandonGameResponse)
def abandon_game(
    game_id: str,
    service: GameService = Depends(get_game_service),
) -> AbandonGameResponse:
    return service.abandon_game(game_id)
