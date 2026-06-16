from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.models import (
    Answer,
    AskQuestionResponse,
    Difficulty,
    GameSession,
    GameStatus,
    Puzzle,
    PuzzleDraft,
    QuestionRecord,
)


def test_answer_display_label_is_stable() -> None:
    response = AskQuestionResponse(answer=Answer.IRRELEVANT)

    assert response.display_answer == "無關"
    assert response.model_dump(mode="json") == {
        "answer": "irrelevant",
        "display_answer": "無關",
    }


def test_puzzle_draft_rejects_invalid_enum() -> None:
    with pytest.raises(ValidationError):
        PuzzleDraft(
            title="題目",
            surface_story="謎面",
            truth="真相",
            key_facts=["事實"],
            forbidden_assumptions=[],
            difficulty="impossible",
        )


def test_public_game_response_does_not_require_hidden_fields() -> None:
    created_at = datetime.now(ZoneInfo("Asia/Taipei"))
    session = GameSession(
        game_id="game-1",
        topic="主題",
        puzzle=Puzzle(
            title="標題",
            surface_story="謎面",
            truth="真相",
            key_facts=["關鍵"],
            forbidden_assumptions=["錯誤假設"],
            difficulty=Difficulty.MEDIUM,
        ),
        questions=[
            QuestionRecord(
                question="他還活著嗎？",
                answer=Answer.YES,
                created_at=created_at,
            )
        ],
        status=GameStatus.PLAYING,
        created_at=created_at,
    )

    public = {
        "game_id": session.game_id,
        "topic": session.topic,
        "surface_story": session.puzzle.surface_story,
        "status": session.status,
        "questions": session.questions,
        "solution_attempts": session.solution_attempts,
    }

    assert "truth" not in public
    assert "key_facts" not in public
    assert "forbidden_assumptions" not in public
