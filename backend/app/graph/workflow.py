from __future__ import annotations

import logging
from time import perf_counter

from langgraph.graph import END, START, StateGraph

from app.config import Settings, get_settings
from app.graph.nodes import (
    answer_question_node,
    expand_truth_node,
    extract_solution_facts_node,
    finalize_puzzle_node,
    generate_core_truth_node,
    generate_assumptions_node,
    interpret_topic_node,
    judge_solution_node,
    review_puzzle_node,
    revision_target,
    route_revision_node,
    should_finalize_or_revise,
    write_surface_story_node,
)
from app.graph.state import PuzzleGraphState, QuestionGraphState, SolutionGraphState
from app.llm.client import LlmClient
from app.models import Puzzle, PuzzleDraft, QuestionJudgement, QuestionRecord, SolutionJudgement
from app.observability import log_event


logger = logging.getLogger("app.graph.workflow")


class SituationPuzzleWorkflow:
    def __init__(self, llm: LlmClient, settings: Settings | None = None) -> None:
        self.llm = llm
        self.settings = settings or get_settings()
        self._puzzle_graph = self._build_puzzle_graph()
        self._question_graph = self._build_question_graph()
        self._solution_graph = self._build_solution_graph()

    def _build_puzzle_graph(self):
        graph = StateGraph(PuzzleGraphState)
        graph.add_node("interpret_topic", interpret_topic_node(self.llm))
        graph.add_node("generate_core_truth", generate_core_truth_node(self.llm))
        graph.add_node("expand_truth", expand_truth_node(self.llm))
        graph.add_node("extract_solution_facts", extract_solution_facts_node(self.llm))
        graph.add_node("write_surface_story", write_surface_story_node(self.llm))
        graph.add_node("generate_assumptions", generate_assumptions_node(self.llm))
        graph.add_node("review_puzzle", review_puzzle_node(self.llm, self.settings))
        graph.add_node("route_revision", route_revision_node(self.settings))
        graph.add_node("finalize_puzzle", finalize_puzzle_node())
        graph.add_edge(START, "interpret_topic")
        graph.add_edge("interpret_topic", "generate_core_truth")
        graph.add_edge("generate_core_truth", "expand_truth")
        graph.add_edge("expand_truth", "extract_solution_facts")
        graph.add_edge("extract_solution_facts", "write_surface_story")
        graph.add_edge("write_surface_story", "generate_assumptions")
        graph.add_edge("generate_assumptions", "review_puzzle")
        graph.add_conditional_edges(
            "review_puzzle",
            should_finalize_or_revise,
            {
                "finalize_puzzle": "finalize_puzzle",
                "route_revision": "route_revision",
            },
        )
        graph.add_conditional_edges(
            "route_revision",
            revision_target,
            {
                "generate_core_truth": "generate_core_truth",
                "expand_truth": "expand_truth",
                "extract_key_facts": "extract_solution_facts",
                "extract_solution_facts": "extract_solution_facts",
                "write_surface_story": "write_surface_story",
                "generate_forbidden_assumptions": "generate_assumptions",
                "generate_assumptions": "generate_assumptions",
            },
        )
        graph.add_edge("finalize_puzzle", END)
        return graph.compile()

    def _build_question_graph(self):
        graph = StateGraph(QuestionGraphState)
        graph.add_node("answer_question", answer_question_node(self.llm))
        graph.add_edge(START, "answer_question")
        graph.add_edge("answer_question", END)
        return graph.compile()

    def _build_solution_graph(self):
        graph = StateGraph(SolutionGraphState)
        graph.add_node("judge_solution", judge_solution_node(self.llm))
        graph.add_edge(START, "judge_solution")
        graph.add_edge("judge_solution", END)
        return graph.compile()

    def generate_puzzle(self, topic: str) -> PuzzleDraft:
        result = self._invoke(
            "generate_puzzle_pipeline",
            self._puzzle_graph,
            {"topic": topic, "revision_count": 0},
        )
        return result["puzzle_draft"]

    def answer_question(
        self,
        puzzle: Puzzle,
        question: str,
        history: list[QuestionRecord],
    ) -> QuestionJudgement:
        result = self._invoke(
            "answer_question",
            self._question_graph,
            {"puzzle": puzzle, "question": question, "history": history},
        )
        return result["judgement"]

    def judge_solution(
        self,
        puzzle: Puzzle,
        solution: str,
        history: list[QuestionRecord],
    ) -> SolutionJudgement:
        result = self._invoke(
            "judge_solution",
            self._solution_graph,
            {"puzzle": puzzle, "solution": solution, "history": history},
        )
        return result["judgement"]

    @staticmethod
    def _invoke(workflow: str, graph, state: dict):
        start = perf_counter()
        log_event(
            logger,
            "graph.invoke.started",
            workflow=workflow,
            state_keys=sorted(state.keys()),
        )
        try:
            result = graph.invoke(state)
        except Exception as exc:
            log_event(
                logger,
                "graph.invoke.failed",
                level=logging.ERROR,
                workflow=workflow,
                duration_ms=round((perf_counter() - start) * 1000, 2),
                exception_type=type(exc).__name__,
            )
            raise
        log_event(
            logger,
            "graph.invoke.finished",
            workflow=workflow,
            output_keys=sorted(result.keys()),
            duration_ms=round((perf_counter() - start) * 1000, 2),
        )
        return result
