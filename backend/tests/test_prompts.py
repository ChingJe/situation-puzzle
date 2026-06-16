from app.config import PuzzleConfig
from app.llm.prompts import (
    answer_question_system_prompt,
    judge_solution_system_prompt,
    puzzle_generation_system_prompt,
)


def test_puzzle_generation_prompt_uses_tested_quality_rules() -> None:
    prompt = puzzle_generation_system_prompt(PuzzleConfig())

    assert "主題忠實度是最高優先" in prompt
    assert "不要弱化主題結果" in prompt
    assert "一個場景、一個異常、一個真相" in prompt
    assert "key_facts：4 到 5 條" in prompt
    assert "surface_story 的每個異常" in prompt


def test_answer_question_prompt_keeps_no_and_irrelevant_valid() -> None:
    prompt = answer_question_system_prompt()

    assert "不可以因為答案是 no 而判 invalid" in prompt
    assert "問題與真相無關" in prompt
    assert "answer=irrelevant" in prompt
    assert "is_valid_question 是 false 時，answer 必須是 null" in prompt


def test_judge_solution_prompt_requires_core_causality() -> None:
    prompt = judge_solution_system_prompt()

    assert "造成謎面異常的真正原因" in prompt
    assert "關鍵行動者做了什麼" in prompt
    assert "只猜到不是偷竊、不是超自然、只是誤會" in prompt
    assert "key_facts 為最低必要門檻" in prompt
