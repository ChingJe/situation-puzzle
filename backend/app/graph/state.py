from __future__ import annotations

from typing import TypedDict

from app.models import (
    CoreTruthDraft,
    ForbiddenAssumptionsDraft,
    KeyFactsDraft,
    Puzzle,
    PuzzleDraft,
    PuzzleReviewResult,
    QuestionJudgement,
    QuestionRecord,
    SolutionJudgement,
    SurfaceStoryDraft,
    TopicInterpretation,
    TruthDraft,
)


class PuzzleGraphState(TypedDict, total=False):
    topic: str
    topic_interpretation: TopicInterpretation
    core_truth: CoreTruthDraft
    truth_draft: TruthDraft
    key_facts_draft: KeyFactsDraft
    surface_story_draft: SurfaceStoryDraft
    forbidden_assumptions_draft: ForbiddenAssumptionsDraft
    review_result: PuzzleReviewResult
    revision_count: int
    last_failed_node: str
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
