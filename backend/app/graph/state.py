from __future__ import annotations

from typing import TypedDict

from app.models import (
    AssumptionsDraft,
    CoreTruthDraft,
    Puzzle,
    PuzzleDraft,
    PuzzleReviewResult,
    QuestionJudgement,
    QuestionRecord,
    SolutionJudgement,
    SolutionFactsDraft,
    SurfaceStoryDraft,
    TopicInterpretation,
    TruthDraft,
)


class PuzzleGraphState(TypedDict, total=False):
    topic: str
    topic_interpretation: TopicInterpretation
    core_truth: CoreTruthDraft
    truth_draft: TruthDraft
    solution_facts_draft: SolutionFactsDraft
    surface_story_draft: SurfaceStoryDraft
    assumptions_draft: AssumptionsDraft
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
