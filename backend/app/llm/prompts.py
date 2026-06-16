from __future__ import annotations

from app.config import PuzzleConfig
from app.models import Puzzle, QuestionRecord


def puzzle_generation_system_prompt(config: PuzzleConfig) -> str:
    return "\n".join(
        [
            "你是海龜湯遊戲的出題主持人。",
            f"所有內容必須使用 {config.language}。",
            "請根據玩家主題創作一題完整海龜湯，謎面只提供異常事件，不直接洩漏真相。",
            f"謎面不得超過 {config.surface_story_max_chars} 個中文字。",
            f"真相長度需介於 {config.truth_min_chars} 到 {config.truth_max_chars} 個中文字。",
            f"關鍵事實需提供 {config.key_facts_min} 到 {config.key_facts_max} 條。",
            f"內容風格：{config.content_style}。",
            "請避免露骨血腥、歧視、真實個資，以及需要專業醫療或法律知識才能解開的情節。",
        ]
    )


def puzzle_generation_user_prompt(topic: str) -> str:
    return f"玩家提供的主題如下，詳細程度不固定，請合理發想：\n{topic}"


def answer_question_system_prompt() -> str:
    return "\n".join(
        [
            "你是海龜湯遊戲主持人，只能判定玩家問題是否為可用是／否回答的問題。",
            "有效問題只能回答 yes、no、irrelevant 三者之一。",
            "若問題不是是非題、要求提示、要求解釋、要求開放式資訊，is_valid_question 必須為 false。",
            "不要提供任何額外說明，不要洩漏真相。",
        ]
    )


def answer_question_user_prompt(
    puzzle: Puzzle,
    question: str,
    history: list[QuestionRecord],
) -> str:
    previous = "\n".join(
        f"- Q: {record.question} / A: {record.display_answer}" for record in history
    )
    return "\n".join(
        [
            f"謎面：{puzzle.surface_story}",
            f"完整真相：{puzzle.truth}",
            "關鍵事實：",
            *[f"- {fact}" for fact in puzzle.key_facts],
            "不應被誤判為真的假設：",
            *[f"- {item}" for item in puzzle.forbidden_assumptions],
            "既有問答：",
            previous or "（尚無）",
            f"玩家問題：{question}",
        ]
    )


def judge_solution_system_prompt() -> str:
    return "\n".join(
        [
            "你是海龜湯遊戲主持人，負責判定玩家提交的完整解答是否已抓到核心真相。",
            "玩家不必逐字命中，但必須涵蓋主要因果、關鍵轉折與事件真相。",
            "只回傳 solved 布林值，不提供提示或解釋。",
        ]
    )


def judge_solution_user_prompt(
    puzzle: Puzzle,
    solution: str,
    history: list[QuestionRecord],
) -> str:
    previous = "\n".join(
        f"- Q: {record.question} / A: {record.display_answer}" for record in history
    )
    return "\n".join(
        [
            f"謎面：{puzzle.surface_story}",
            f"完整真相：{puzzle.truth}",
            "關鍵事實：",
            *[f"- {fact}" for fact in puzzle.key_facts],
            "既有問答：",
            previous or "（尚無）",
            f"玩家解答：{solution}",
        ]
    )
