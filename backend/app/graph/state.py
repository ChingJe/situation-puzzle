from __future__ import annotations

from typing import TypedDict

from app.models import Puzzle, PuzzleDraft, QuestionJudgement, QuestionRecord, SolutionJudgement


class PuzzleGraphState(TypedDict, total=False):
    topic: str
    puzzle_draft: PuzzleDraft


class QuestionGraphState(TypedDict, total=False):
    puzzle: Puzzle
    question: str
    history: list[QuestionRecord]
    judgement: QuestionJudgement


class SolutionGraphState(TypedDict, total=False):
    puzzle: Puzzle
    solution: str
    history: list[QuestionRecord]
    judgement: SolutionJudgement
