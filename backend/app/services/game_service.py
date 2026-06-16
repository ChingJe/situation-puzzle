from __future__ import annotations

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.errors import ApiErrorCode, AppError
from app.graph.workflow import SituationPuzzleWorkflow
from app.models import (
    AbandonGameResponse,
    Answer,
    AskQuestionResponse,
    CreateGameResponse,
    GameSession,
    GameStatus,
    PublicGameResponse,
    Puzzle,
    QuestionRecord,
    SolutionAttempt,
    SubmitSolutionResponse,
)
from app.storage import GameStorage


TAIPEI = ZoneInfo("Asia/Taipei")


def now() -> datetime:
    return datetime.now(TAIPEI)


class GameService:
    def __init__(
        self,
        *,
        workflow: SituationPuzzleWorkflow,
        storage: GameStorage,
    ) -> None:
        self.workflow = workflow
        self.storage = storage
        self.sessions: dict[str, GameSession] = {}

    def create_game(self, topic: str) -> CreateGameResponse:
        draft = self.workflow.generate_puzzle(topic)
        session = GameSession(
            game_id=str(uuid4()),
            topic=topic,
            puzzle=Puzzle.from_draft(draft),
            created_at=now(),
        )
        self.sessions[session.game_id] = session
        return CreateGameResponse(
            game_id=session.game_id,
            surface_story=session.puzzle.surface_story,
            status=session.status,
        )

    def get_game(self, game_id: str) -> PublicGameResponse:
        session = self._get_session(game_id)
        return self._public_game_response(session)

    def ask_question(self, game_id: str, question: str) -> AskQuestionResponse:
        session = self._get_playing_session(game_id)
        judgement = self.workflow.answer_question(
            session.puzzle,
            question,
            session.questions,
        )
        if not judgement.is_valid_question or judgement.answer is None:
            raise AppError(ApiErrorCode.INVALID_QUESTION, status_code=400)

        record = QuestionRecord(
            question=question,
            answer=Answer(judgement.answer),
            created_at=now(),
        )
        session.questions.append(record)
        return AskQuestionResponse(answer=record.answer)

    def submit_solution(
        self,
        game_id: str,
        solution: str,
    ) -> SubmitSolutionResponse:
        session = self._get_playing_session(game_id)
        judgement = self.workflow.judge_solution(
            session.puzzle,
            solution,
            session.questions,
        )
        attempt = SolutionAttempt(
            solution=solution,
            solved=judgement.solved,
            created_at=now(),
        )
        session.solution_attempts.append(attempt)

        if not judgement.solved:
            return SubmitSolutionResponse(
                solved=False,
                message="尚未解開",
                status=session.status,
            )

        session.status = GameStatus.SOLVED
        session.ended_at = now()
        self._persist_completed(session)
        return SubmitSolutionResponse(
            solved=True,
            message="成功解開",
            status=session.status,
            truth=session.puzzle.truth,
        )

    def abandon_game(self, game_id: str) -> AbandonGameResponse:
        session = self._get_playing_session(game_id)
        session.status = GameStatus.ABANDONED
        session.ended_at = now()
        self._persist_completed(session)
        return AbandonGameResponse(status=session.status, truth=session.puzzle.truth)

    def _persist_completed(self, session: GameSession) -> None:
        self.storage.save_completed_game(session.to_completed_record())

    def _get_session(self, game_id: str) -> GameSession:
        try:
            return self.sessions[game_id]
        except KeyError as exc:
            raise AppError(ApiErrorCode.GAME_NOT_FOUND, status_code=404) from exc

    def _get_playing_session(self, game_id: str) -> GameSession:
        session = self._get_session(game_id)
        if session.status != GameStatus.PLAYING:
            raise AppError(ApiErrorCode.GAME_ALREADY_ENDED, status_code=409)
        return session

    @staticmethod
    def _public_game_response(session: GameSession) -> PublicGameResponse:
        truth = session.puzzle.truth if session.status != GameStatus.PLAYING else None
        return PublicGameResponse(
            game_id=session.game_id,
            topic=session.topic,
            surface_story=session.puzzle.surface_story,
            status=session.status,
            questions=session.questions,
            solution_attempts=session.solution_attempts,
            truth=truth,
        )
