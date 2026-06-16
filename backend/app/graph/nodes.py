from __future__ import annotations

from app.llm.client import LlmClient
from app.graph.state import PuzzleGraphState, QuestionGraphState, SolutionGraphState


def generate_puzzle_node(llm: LlmClient):
    def node(state: PuzzleGraphState) -> PuzzleGraphState:
        return {"puzzle_draft": llm.generate_puzzle(state["topic"])}

    return node


def answer_question_node(llm: LlmClient):
    def node(state: QuestionGraphState) -> QuestionGraphState:
        return {
            "judgement": llm.answer_question(
                state["puzzle"],
                state["question"],
                state.get("history", []),
            )
        }

    return node


def judge_solution_node(llm: LlmClient):
    def node(state: SolutionGraphState) -> SolutionGraphState:
        return {
            "judgement": llm.judge_solution(
                state["puzzle"],
                state["solution"],
                state.get("history", []),
            )
        }

    return node
