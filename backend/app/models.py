from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


class GameStatus(StrEnum):
    PLAYING = "playing"
    SOLVED = "solved"
    ABANDONED = "abandoned"


class Answer(StrEnum):
    YES = "yes"
    NO = "no"
    IRRELEVANT = "irrelevant"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


ANSWER_LABELS: dict[Answer, str] = {
    Answer.YES: "是",
    Answer.NO: "否",
    Answer.IRRELEVANT: "無關",
}


class ApiModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        use_enum_values=False,
    )


class PuzzleDraft(ApiModel):
    schema_version: int = 1
    title: str = Field(min_length=1, max_length=80)
    surface_story: str = Field(min_length=1)
    truth: str = Field(min_length=1)
    key_facts: list[str] = Field(min_length=1)
    core_mystery: str = ""
    core_truth: str = ""
    required_solution_facts: list[RequiredSolutionFact] = Field(default_factory=list)
    supporting_facts: list[SupportingFact] = Field(default_factory=list)
    misleading_assumptions: list[str] = Field(default_factory=list)
    forbidden_assumptions: list[str] = Field(default_factory=list)
    quality_notes: PuzzleQualityNotes = Field(default_factory=lambda: PuzzleQualityNotes())
    difficulty: Difficulty = Difficulty.MEDIUM


class TopicInterpretation(ApiModel):
    title: str = Field(min_length=1, max_length=80)
    scene: str = Field(min_length=1, max_length=120)
    objects: list[str] = Field(default_factory=list, max_length=6)
    actors: list[str] = Field(default_factory=list, max_length=4)
    explicit_results: list[str] = Field(default_factory=list, max_length=4)
    hard_constraints: list[str] = Field(default_factory=list, max_length=6)
    open_space: str = Field(min_length=1, max_length=300)


class CoreTruthDraft(ApiModel):
    core_truth: str = Field(min_length=1, max_length=180)
    cause: str = Field(min_length=1, max_length=120)
    actor_action: str = Field(min_length=1, max_length=120)
    abnormal_result: str = Field(min_length=1, max_length=120)
    misdirection: str = Field(min_length=1, max_length=120)


class RequiredSolutionFact(ApiModel):
    id: str = Field(min_length=1, max_length=40)
    fact: str = Field(min_length=1, max_length=180)
    role: Literal["cause", "actor", "action", "result", "misdirection", "other"] = "other"


class SupportingFact(ApiModel):
    id: str = Field(min_length=1, max_length=40)
    fact: str = Field(min_length=1, max_length=180)


class SolutionFactsDraft(ApiModel):
    required_solution_facts: list[RequiredSolutionFact] = Field(default_factory=list)
    supporting_facts: list[SupportingFact] = Field(default_factory=list)

    @property
    def key_facts(self) -> list[str]:
        return [
            *[item.fact for item in self.required_solution_facts],
            *[item.fact for item in self.supporting_facts],
        ]


class PuzzleQualityNotes(ApiModel):
    abnormal_result: str = ""
    misdirection: str = ""
    answer_shape: str = ""


class TruthDraft(ApiModel):
    truth: str = Field(min_length=1)


class KeyFactsDraft(ApiModel):
    key_facts: list[str] = Field(min_length=1)


class SurfaceStoryDraft(ApiModel):
    surface_story: str = Field(min_length=1)


class AssumptionsDraft(ApiModel):
    misleading_assumptions: list[str] = Field(default_factory=list)
    forbidden_assumptions: list[str] = Field(default_factory=list)


class PuzzleReviewResult(ApiModel):
    passed: bool
    severity: Literal["minor", "major", "critical"] = "minor"
    target_node: Literal[
        "generate_core_truth",
        "expand_truth",
        "extract_key_facts",
        "extract_solution_facts",
        "write_surface_story",
        "generate_forbidden_assumptions",
        "generate_assumptions",
        "finalize_puzzle",
    ] = "finalize_puzzle"
    issues: list[str] = Field(default_factory=list)
    revision_instruction: str = ""


class QuestionJudgement(ApiModel):
    is_valid_question: bool
    answer: Answer | None = None


class SolutionJudgement(ApiModel):
    solved: bool
    matched_required_fact_ids: list[str] = Field(default_factory=list)
    matched_from_history_fact_ids: list[str] = Field(default_factory=list)
    conflicting_assumptions: list[str] = Field(default_factory=list)
    internal_reason: str = ""


class Puzzle(ApiModel):
    schema_version: int = 1
    title: str
    surface_story: str
    truth: str
    key_facts: list[str]
    core_mystery: str = ""
    core_truth: str = ""
    required_solution_facts: list[RequiredSolutionFact] = Field(default_factory=list)
    supporting_facts: list[SupportingFact] = Field(default_factory=list)
    misleading_assumptions: list[str] = Field(default_factory=list)
    forbidden_assumptions: list[str]
    quality_notes: PuzzleQualityNotes = Field(default_factory=lambda: PuzzleQualityNotes())
    difficulty: Difficulty

    @classmethod
    def from_draft(cls, draft: PuzzleDraft) -> Puzzle:
        return cls(**draft.model_dump())


class QuestionRecord(ApiModel):
    question: str
    answer: Answer
    display_answer: str = ""
    created_at: datetime

    @model_validator(mode="after")
    def sync_display_answer(self) -> QuestionRecord:
        self.display_answer = ANSWER_LABELS[self.answer]
        return self


class SolutionAttempt(ApiModel):
    solution: str
    solved: bool
    created_at: datetime


class GameSession(ApiModel):
    game_id: str
    topic: str
    puzzle: Puzzle
    status: GameStatus = GameStatus.PLAYING
    questions: list[QuestionRecord] = Field(default_factory=list)
    solution_attempts: list[SolutionAttempt] = Field(default_factory=list)
    created_at: datetime
    ended_at: datetime | None = None

    def to_completed_record(self) -> CompletedGameRecord:
        if self.status == GameStatus.PLAYING or self.ended_at is None:
            raise ValueError("Only ended games can be converted to completed records.")
        return CompletedGameRecord(
            game_id=self.game_id,
            topic=self.topic,
            title=self.puzzle.title,
            surface_story=self.puzzle.surface_story,
            truth=self.puzzle.truth,
            key_facts=self.puzzle.key_facts,
            schema_version=self.puzzle.schema_version,
            core_mystery=self.puzzle.core_mystery,
            core_truth=self.puzzle.core_truth,
            required_solution_facts=self.puzzle.required_solution_facts,
            supporting_facts=self.puzzle.supporting_facts,
            misleading_assumptions=self.puzzle.misleading_assumptions,
            forbidden_assumptions=self.puzzle.forbidden_assumptions,
            quality_notes=self.puzzle.quality_notes,
            difficulty=self.puzzle.difficulty,
            questions=self.questions,
            solution_attempts=self.solution_attempts,
            status=self.status,
            created_at=self.created_at,
            ended_at=self.ended_at,
        )


class CompletedGameRecord(ApiModel):
    game_id: str
    topic: str
    schema_version: int = 1
    title: str
    surface_story: str
    truth: str
    key_facts: list[str]
    core_mystery: str = ""
    core_truth: str = ""
    required_solution_facts: list[RequiredSolutionFact] = Field(default_factory=list)
    supporting_facts: list[SupportingFact] = Field(default_factory=list)
    misleading_assumptions: list[str] = Field(default_factory=list)
    forbidden_assumptions: list[str]
    quality_notes: PuzzleQualityNotes = Field(default_factory=lambda: PuzzleQualityNotes())
    difficulty: Difficulty
    questions: list[QuestionRecord]
    solution_attempts: list[SolutionAttempt]
    status: Literal[GameStatus.SOLVED, GameStatus.ABANDONED]
    created_at: datetime
    ended_at: datetime


class HistoryItem(ApiModel):
    game_id: str
    title: str
    topic: str
    status: Literal[GameStatus.SOLVED, GameStatus.ABANDONED]
    question_count: int
    created_at: datetime
    ended_at: datetime


class CreateGameRequest(ApiModel):
    topic: str = Field(min_length=1, max_length=2000)


class CreateGameResponse(ApiModel):
    game_id: str
    surface_story: str
    status: GameStatus


class PublicGameResponse(ApiModel):
    game_id: str
    topic: str
    surface_story: str
    status: GameStatus
    questions: list[QuestionRecord]
    solution_attempts: list[SolutionAttempt]
    truth: str | None = None


class AskQuestionRequest(ApiModel):
    question: str = Field(min_length=1, max_length=1000)


class AskQuestionResponse(ApiModel):
    answer: Answer

    @computed_field
    @property
    def display_answer(self) -> str:
        return ANSWER_LABELS[self.answer]


class SubmitSolutionRequest(ApiModel):
    solution: str = Field(min_length=1, max_length=4000)


class SubmitSolutionResponse(ApiModel):
    solved: bool
    message: str
    status: GameStatus
    truth: str | None = None


class AbandonGameResponse(ApiModel):
    status: GameStatus
    truth: str


class HistoryListResponse(ApiModel):
    items: list[HistoryItem]


class HealthComponent(ApiModel):
    status: str
    error: str | None = None


class HealthResponse(ApiModel):
    status: Literal["ok", "degraded"]
    backend: dict[str, str]
    llm: dict[str, object]
    storage: dict[str, object]
