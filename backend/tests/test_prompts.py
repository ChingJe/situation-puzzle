from app.config import PuzzleConfig, PuzzleGenerationConfig
from app.llm.prompts import (
    answer_question_system_prompt,
    generate_core_truth_system_prompt,
    judge_solution_user_prompt,
    judge_solution_system_prompt,
    puzzle_generation_system_prompt,
    review_puzzle_system_prompt,
    write_surface_story_system_prompt,
)
from app.llm.client import FakeLlmClient


def test_puzzle_generation_prompt_uses_tested_quality_rules() -> None:
    prompt = puzzle_generation_system_prompt(PuzzleConfig())

    assert "主題忠實度是最高優先" in prompt
    assert "不要弱化主題結果" in prompt
    assert "一個場景、一個異常、一個真相" in prompt
    assert "key_facts：4 到 5 條" in prompt
    assert "surface_story 的每個異常" in prompt


def test_pipeline_prompts_preserve_generation_quality_rules() -> None:
    core_prompt = generate_core_truth_system_prompt(PuzzleConfig())
    surface_prompt = write_surface_story_system_prompt(
        PuzzleConfig(),
        PuzzleGenerationConfig(),
    )
    review_prompt = review_puzzle_system_prompt(PuzzleConfig())

    assert "一個主要異常、一條核心因果鏈" in core_prompt
    assert "不可否定 topic_interpretation.hard_constraints" in core_prompt
    assert "不得把核心原因寫成標籤貼錯" in core_prompt
    assert "買了不拿以製造可見訊號" in core_prompt
    assert "謎面中的客觀陳述必須被 truth 承認為客觀事實" in surface_prompt
    assert "如果某件事只是角色誤會，不可寫成客觀事實" in surface_prompt
    assert "不可寫出真正行動者的關鍵行動" in surface_prompt
    assert "真正原因提供至少一個玩家可觀察的公平線索" in surface_prompt
    assert "天花板附近有水痕" in surface_prompt
    assert "監視畫面像是" in surface_prompt
    assert "謎面客觀事實不可被 truth 否定" in review_prompt
    assert "標籤貼錯、看錯標示" in review_prompt
    assert "required cause 的可觀察入口" in review_prompt
    assert "水管破裂但謎面沒有水痕" in review_prompt
    assert "未加視角限定的強客觀敘述" in review_prompt
    assert "指定最小必要修正節點" in review_prompt


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
    assert "required_solution_facts 為最低必要門檻" in prompt
    assert "supporting_facts 只輔助理解" in prompt


def test_judge_solution_user_prompt_contains_solution_context() -> None:
    from app.models import Puzzle

    puzzle = Puzzle.from_draft(FakeLlmClient.default_puzzle())

    prompt = judge_solution_user_prompt(puzzle, "玩家提交的解答", [])

    assert "謎面：" in prompt
    assert puzzle.surface_story in prompt
    assert "完整真相：" in prompt
    assert "玩家提交的解答" in prompt
