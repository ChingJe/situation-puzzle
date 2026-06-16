from __future__ import annotations

from datetime import datetime
import logging
from time import perf_counter
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.config import get_settings
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
from app.observability import bind_log_context, log_event, log_raw_message
from app.storage import GameStorage


TAIPEI = ZoneInfo("Asia/Taipei")
logger = logging.getLogger("app.services.game_service")


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
        self.settings = get_settings()
        self.sessions: dict[str, GameSession] = {}

    def create_game(self, topic: str) -> CreateGameResponse:
        start = perf_counter()
        log_event(
            logger,
            "game.create.started",
            topic_length=len(topic),
            active_session_count=len(self.sessions),
        )
        if self.settings.logging.raw_message_include_player_messages:
            log_raw_message(
                self.settings,
                "player.topic",
                "create_game",
                topic,
                content_type="text",
            )
        draft = self.workflow.generate_puzzle(topic)
        session = GameSession(
            game_id=str(uuid4()),
            topic=topic,
            puzzle=Puzzle.from_draft(draft),
            created_at=now(),
        )
        self.sessions[session.game_id] = session
        with bind_log_context(game_id=session.game_id):
            log_event(
                logger,
                "game.created",
                game_id=session.game_id,
                title=session.puzzle.title,
                surface_story_length=len(session.puzzle.surface_story),
                difficulty=session.puzzle.difficulty.value,
                duration_ms=round((perf_counter() - start) * 1000, 2),
            )
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
        start = perf_counter()
        with bind_log_context(game_id=game_id):
            log_event(
                logger,
                "question.answer.started",
                game_id=game_id,
                question_length=len(question),
                question_count_before=len(session.questions),
            )
            if self.settings.logging.raw_message_include_player_messages:
                log_raw_message(
                    self.settings,
                    "player.question",
                    "ask_question",
                    question,
                    content_type="text",
                    game_id=game_id,
                )
            judgement = self.workflow.answer_question(
                session.puzzle,
                question,
                session.questions,
            )
            if not judgement.is_valid_question or judgement.answer is None:
                log_event(
                    logger,
                    "question.invalid",
                    level=logging.WARNING,
                    game_id=game_id,
                    question_length=len(question),
                    error_code=ApiErrorCode.INVALID_QUESTION.value,
                    duration_ms=round((perf_counter() - start) * 1000, 2),
                )
                raise AppError(ApiErrorCode.INVALID_QUESTION, status_code=400)

            record = QuestionRecord(
                question=question,
                answer=Answer(judgement.answer),
                created_at=now(),
            )
            session.questions.append(record)
            log_event(
                logger,
                "question.answered",
                game_id=game_id,
                answer=record.answer.value,
                question_count_after=len(session.questions),
                duration_ms=round((perf_counter() - start) * 1000, 2),
            )
            return AskQuestionResponse(answer=record.answer)

    def submit_solution(
        self,
        game_id: str,
        solution: str,
    ) -> SubmitSolutionResponse:
        session = self._get_playing_session(game_id)
        start = perf_counter()
        with bind_log_context(game_id=game_id):
            log_event(
                logger,
                "solution.judge.started",
                game_id=game_id,
                solution_length=len(solution),
                attempt_count_before=len(session.solution_attempts),
            )
            if self.settings.logging.raw_message_include_player_messages:
                log_raw_message(
                    self.settings,
                    "player.solution",
                    "submit_solution",
                    solution,
                    content_type="text",
                    game_id=game_id,
                )
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
                log_event(
                    logger,
                    "solution.judged",
                    game_id=game_id,
                    solved=False,
                    status=session.status.value,
                    attempt_count_after=len(session.solution_attempts),
                    duration_ms=round((perf_counter() - start) * 1000, 2),
                )
                return SubmitSolutionResponse(
                    solved=False,
                    message="尚未解開",
                    status=session.status,
                )

            session.status = GameStatus.SOLVED
            session.ended_at = now()
            self._persist_completed(session)
            log_event(
                logger,
                "solution.judged",
                game_id=game_id,
                solved=True,
                status=session.status.value,
                attempt_count_after=len(session.solution_attempts),
                duration_ms=round((perf_counter() - start) * 1000, 2),
            )
            return SubmitSolutionResponse(
                solved=True,
                message="成功解開",
                status=session.status,
                truth=session.puzzle.truth,
            )

    def abandon_game(self, game_id: str) -> AbandonGameResponse:
        session = self._get_playing_session(game_id)
        with bind_log_context(game_id=game_id):
            session.status = GameStatus.ABANDONED
            session.ended_at = now()
            self._persist_completed(session)
            log_event(
                logger,
                "game.abandoned",
                game_id=game_id,
                question_count=len(session.questions),
                attempt_count=len(session.solution_attempts),
            )
            return AbandonGameResponse(status=session.status, truth=session.puzzle.truth)

    def _persist_completed(self, session: GameSession) -> None:
        start = perf_counter()
        self.storage.save_completed_game(session.to_completed_record())
        log_event(
            logger,
            "game.finalized",
            game_id=session.game_id,
            status=session.status.value,
            ended_at=session.ended_at.isoformat() if session.ended_at else None,
            duration_ms=round((perf_counter() - start) * 1000, 2),
        )

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
