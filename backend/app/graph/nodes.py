from __future__ import annotations

import logging
from time import perf_counter

from app.llm.client import LlmClient
from app.graph.state import PuzzleGraphState, QuestionGraphState, SolutionGraphState
from app.observability import log_event


logger = logging.getLogger("app.graph.nodes")


def generate_puzzle_node(llm: LlmClient):
    def node(state: PuzzleGraphState) -> PuzzleGraphState:
        return _run_node(
            "generate_puzzle",
            state,
            lambda: {"puzzle_draft": llm.generate_puzzle(state["topic"])},
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


def _run_node(name: str, state: dict, callback):
    start = perf_counter()
    log_event(
        logger,
        "graph.node.started",
        node=name,
        state_keys=sorted(state.keys()),
    )
    try:
        result = callback()
    except Exception as exc:
        log_event(
            logger,
            "graph.node.failed",
            level=logging.ERROR,
            node=name,
            duration_ms=round((perf_counter() - start) * 1000, 2),
            exception_type=type(exc).__name__,
        )
        raise
    log_event(
        logger,
        "graph.node.finished",
        node=name,
        output_keys=sorted(result.keys()),
        duration_ms=round((perf_counter() - start) * 1000, 2),
    )
    return result
