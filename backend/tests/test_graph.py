from app.graph.workflow import SituationPuzzleWorkflow
from app.llm.client import FakeLlmClient
from app.models import Answer, Puzzle, QuestionJudgement, SolutionJudgement


def test_graph_uses_fake_llm_for_full_task_set() -> None:
    workflow = SituationPuzzleWorkflow(
        FakeLlmClient(
            question_judgements=[QuestionJudgement(is_valid_question=True, answer=Answer.NO)],
            solution_judgements=[SolutionJudgement(solved=True)],
        )
    )

    draft = workflow.generate_puzzle("雨夜")
    puzzle = Puzzle.from_draft(draft)
    question = workflow.answer_question(puzzle, "男子死亡了嗎？", [])
    solution = workflow.judge_solution(puzzle, "他沒有死亡，只是取消婚禮。", [])

    assert draft.title == "雨夜發票"
    assert question.answer == Answer.NO
    assert solution.solved is True
