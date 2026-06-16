from __future__ import annotations

import logging
import re
from time import perf_counter

from app.config import Settings
from app.errors import ApiErrorCode, AppError
from app.llm.client import LlmClient
from app.graph.state import PuzzleGraphState, QuestionGraphState, SolutionGraphState
from app.models import Difficulty, PuzzleDraft, PuzzleQualityNotes, PuzzleReviewResult
from app.observability import log_event


logger = logging.getLogger("app.graph.nodes")


def interpret_topic_node(llm: LlmClient):
    def node(state: PuzzleGraphState) -> PuzzleGraphState:
        return _run_node(
            "interpret_topic",
            state,
            lambda: {"topic_interpretation": llm.interpret_topic(state["topic"])},
        )

    return node


def generate_core_truth_node(llm: LlmClient):
    def node(state: PuzzleGraphState) -> PuzzleGraphState:
        return _run_node(
            "generate_core_truth",
            state,
            lambda: {
                "core_truth": llm.generate_core_truth(
                    state["topic"],
                    state["topic_interpretation"],
                    _review_instruction_for(state, "generate_core_truth"),
                )
            },
        )

    return node


def expand_truth_node(llm: LlmClient):
    def node(state: PuzzleGraphState) -> PuzzleGraphState:
        return _run_node(
            "expand_truth",
            state,
            lambda: {
                "truth_draft": llm.expand_truth(
                    state["topic"],
                    state["topic_interpretation"],
                    state["core_truth"],
                    _review_instruction_for(state, "expand_truth"),
                )
            },
        )

    return node


def extract_solution_facts_node(llm: LlmClient):
    def node(state: PuzzleGraphState) -> PuzzleGraphState:
        return _run_node(
            "extract_solution_facts",
            state,
            lambda: {
                "solution_facts_draft": llm.extract_solution_facts(
                    state["core_truth"],
                    state["truth_draft"],
                    _review_instruction_for(state, "extract_solution_facts"),
                )
            },
        )

    return node


def write_surface_story_node(llm: LlmClient):
    def node(state: PuzzleGraphState) -> PuzzleGraphState:
        return _run_node(
            "write_surface_story",
            state,
            lambda: {
                "surface_story_draft": llm.write_surface_story(
                    state["topic"],
                    state["topic_interpretation"],
                    state["truth_draft"],
                    state["solution_facts_draft"],
                    _review_instruction_for(state, "write_surface_story"),
                )
            },
        )

    return node


def generate_assumptions_node(llm: LlmClient):
    def node(state: PuzzleGraphState) -> PuzzleGraphState:
        return _run_node(
            "generate_assumptions",
            state,
            lambda: {
                "assumptions_draft": llm.generate_assumptions(
                    state["truth_draft"],
                    state["solution_facts_draft"],
                    state["surface_story_draft"],
                )
            },
        )

    return node


def review_puzzle_node(llm: LlmClient, settings: Settings):
    def node(state: PuzzleGraphState) -> PuzzleGraphState:
        return _run_node(
            "review_puzzle",
            state,
            lambda: _review_puzzle(state, llm, settings),
        )

    return node


def route_revision_node(settings: Settings):
    def node(state: PuzzleGraphState) -> PuzzleGraphState:
        return _run_node(
            "route_revision",
            state,
            lambda: _route_revision(state, settings),
        )

    return node


def finalize_puzzle_node():
    def node(state: PuzzleGraphState) -> PuzzleGraphState:
        return _run_node(
            "finalize_puzzle",
            state,
            lambda: {
                "puzzle_draft": PuzzleDraft(
                    schema_version=2,
                    title=state["topic_interpretation"].title,
                    surface_story=state["surface_story_draft"].surface_story,
                    truth=state["truth_draft"].truth,
                    key_facts=state["solution_facts_draft"].key_facts,
                    core_mystery=state["core_truth"].abnormal_result,
                    core_truth=state["core_truth"].core_truth,
                    required_solution_facts=state[
                        "solution_facts_draft"
                    ].required_solution_facts,
                    supporting_facts=state["solution_facts_draft"].supporting_facts,
                    misleading_assumptions=state[
                        "assumptions_draft"
                    ].misleading_assumptions,
                    forbidden_assumptions=state["assumptions_draft"].forbidden_assumptions,
                    quality_notes=PuzzleQualityNotes(
                        abnormal_result=state["core_truth"].abnormal_result,
                        misdirection=state["core_truth"].misdirection,
                        answer_shape="玩家應說明真正原因、關鍵行動、造成的反常結果與表面誤導。",
                    ),
                    difficulty=Difficulty.MEDIUM,
                )
            },
        )

    return node


def answer_question_node(llm: LlmClient):
    def node(state: QuestionGraphState) -> QuestionGraphState:
        return _run_node(
            "answer_question",
            state,
            lambda: {
                "judgement": llm.answer_question(
                    state["puzzle"],
                    state["question"],
                    state.get("history", []),
                )
            },
        )

    return node


def judge_solution_node(llm: LlmClient):
    def node(state: SolutionGraphState) -> SolutionGraphState:
        return _run_node(
            "judge_solution",
            state,
            lambda: {
                "judgement": llm.judge_solution(
                    state["puzzle"],
                    state["solution"],
                    state.get("history", []),
                )
            },
        )

    return node


def should_finalize_or_revise(state: PuzzleGraphState) -> str:
    review = state["review_result"]
    return "finalize_puzzle" if review.passed else "route_revision"


def revision_target(state: PuzzleGraphState) -> str:
    return state["last_failed_node"]


def _run_node(name: str, state: dict, callback):
    start = perf_counter()
    log_event(
        logger,
        "graph.node.started",
        node=name,
        state_keys=sorted(state.keys()),
        revision_count=state.get("revision_count", 0),
    )
    try:
        result = callback()
    except Exception as exc:
        log_event(
            logger,
            "graph.node.failed",
            level=logging.ERROR,
            node=name,
            revision_count=state.get("revision_count", 0),
            duration_ms=round((perf_counter() - start) * 1000, 2),
            exception_type=type(exc).__name__,
        )
        raise
    log_event(
        logger,
        "graph.node.finished",
        node=name,
        output_keys=sorted(result.keys()),
        revision_count=state.get("revision_count", 0),
        **_review_log_fields(result),
        duration_ms=round((perf_counter() - start) * 1000, 2),
    )
    return result


def _review_puzzle(
    state: PuzzleGraphState,
    llm: LlmClient,
    settings: Settings,
) -> PuzzleGraphState:
    gate_result = _run_deterministic_gate(state, settings)
    if gate_result is not None:
        return {"review_result": gate_result}

    if not settings.puzzle_generation.reviewer_enabled:
        return {
            "review_result": PuzzleReviewResult(
                passed=True,
                target_node="finalize_puzzle",
            )
        }

    review = llm.review_puzzle(
        state["topic"],
        state["topic_interpretation"],
        state["core_truth"],
        state["truth_draft"],
        state["solution_facts_draft"],
        state["surface_story_draft"],
        state["assumptions_draft"],
    )
    return {"review_result": review}


def _route_revision(state: PuzzleGraphState, settings: Settings) -> PuzzleGraphState:
    revision_count = state.get("revision_count", 0)
    review = state["review_result"]
    if revision_count >= settings.puzzle_generation.max_revision_rounds:
        log_event(
            logger,
            "graph.revision.exhausted",
            level=logging.ERROR,
            revision_count=revision_count,
            max_revision_rounds=settings.puzzle_generation.max_revision_rounds,
            review_target_node=review.target_node,
            issue_count=len(review.issues),
        )
        raise AppError(ApiErrorCode.LLM_OUTPUT_INVALID, status_code=500)
    if review.target_node == "finalize_puzzle":
        raise AppError(ApiErrorCode.LLM_OUTPUT_INVALID, status_code=500)
    return {
        "revision_count": revision_count + 1,
        "last_failed_node": review.target_node,
    }


def _run_deterministic_gate(
    state: PuzzleGraphState,
    settings: Settings,
) -> PuzzleReviewResult | None:
    if not settings.puzzle_generation.deterministic_gate_enabled:
        return None

    issues: list[str] = []
    target_node = "finalize_puzzle"
    surface_story = state["surface_story_draft"].surface_story.strip()
    truth = state["truth_draft"].truth.strip()
    solution_facts = state["solution_facts_draft"]
    required_facts = [
        fact.fact.strip()
        for fact in solution_facts.required_solution_facts
        if fact.fact.strip()
    ]
    supporting_facts = [
        fact.fact.strip() for fact in solution_facts.supporting_facts if fact.fact.strip()
    ]
    forbidden = [
        item.strip()
        for item in state["assumptions_draft"].forbidden_assumptions
        if item.strip()
    ]
    low_playability_terms = (
        "正常補貨",
        "正常打掃",
        "正常清潔",
        "正常盤點",
        "例行盤點",
        "例行檢查",
        "只是看錯",
        "只是誤會",
    )

    if len(surface_story) > settings.puzzle_generation.strict_surface_story_max_chars:
        issues.append("謎面超過字數上限")
        target_node = "write_surface_story"
    if not surface_story:
        issues.append("謎面為空")
        target_node = "write_surface_story"
    if re.search(r"(其實|原來|因為|真相)", surface_story):
        issues.append("謎面疑似包含解釋詞")
        target_node = "write_surface_story"
    if _sentence_count(surface_story) > 2 or re.search(
        r"(更奇怪的是|同時|另外|另一方面)",
        surface_story,
    ):
        issues.append("謎面疑似包含多個主要異常")
        target_node = "write_surface_story"

    if len(truth) < settings.puzzle_generation.strict_truth_min_chars:
        issues.append("真相低於字數下限")
        target_node = _prefer_earlier_target(target_node, "expand_truth")
    if len(truth) > settings.puzzle_generation.strict_truth_max_chars:
        issues.append("真相超過字數上限")
        target_node = _prefer_earlier_target(target_node, "expand_truth")

    if any(term in state["core_truth"].core_truth for term in low_playability_terms):
        issues.append("核心真相疑似只是直覺日常流程或單純誤會")
        target_node = _prefer_earlier_target(target_node, "generate_core_truth")

    if not 2 <= len(required_facts) <= 4:
        issues.append("必要解答事實條數不符合設定")
        target_node = _prefer_earlier_target(target_node, "extract_solution_facts")

    if not required_facts or len(required_facts) + len(supporting_facts) < 3:
        issues.append("解答事實不足以支撐問答與通關判定")
        target_node = _prefer_earlier_target(target_node, "extract_solution_facts")

    if not 2 <= len(forbidden) <= 3:
        issues.append("錯誤假設條數不符合設定")
        target_node = _prefer_earlier_target(
            target_node,
            "generate_assumptions",
        )

    if not issues:
        return None
    return PuzzleReviewResult(
        passed=False,
        severity="major",
        target_node=target_node,
        issues=issues,
        revision_instruction="；".join(issues),
    )


def _prefer_earlier_target(current: str, candidate: str) -> str:
    order = {
        "generate_core_truth": 0,
        "expand_truth": 1,
        "extract_key_facts": 2,
        "extract_solution_facts": 2,
        "write_surface_story": 3,
        "generate_forbidden_assumptions": 4,
        "generate_assumptions": 4,
        "finalize_puzzle": 5,
    }
    return candidate if order[candidate] < order[current] else current


def _sentence_count(text: str) -> int:
    return len([part for part in re.split(r"[。！？!?]+", text) if part.strip()])


def _review_instruction_for(state: PuzzleGraphState, target_node: str) -> str | None:
    review = state.get("review_result")
    if not review or review.passed:
        return None
    aliases = {
        "extract_solution_facts": {"extract_solution_facts", "extract_key_facts"},
        "generate_assumptions": {
            "generate_assumptions",
            "generate_forbidden_assumptions",
        },
    }
    valid_targets = aliases.get(target_node, {target_node})
    if review.target_node not in valid_targets:
        return None
    return review.revision_instruction or "請依 reviewer issues 修正。"


def _review_log_fields(result: dict) -> dict[str, object]:
    review = result.get("review_result")
    if not isinstance(review, PuzzleReviewResult):
        return {}
    return {
        "review_passed": review.passed,
        "review_target_node": review.target_node,
        "issue_count": len(review.issues),
    }
