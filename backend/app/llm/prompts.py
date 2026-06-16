from __future__ import annotations

from app.config import PuzzleConfig
from app.models import Puzzle, QuestionRecord


def puzzle_generation_system_prompt(config: PuzzleConfig) -> str:
    surface_story_max_chars = min(config.surface_story_max_chars, 120)
    truth_max_chars = min(config.truth_max_chars, 360)
    if truth_max_chars < config.truth_min_chars:
        truth_max_chars = config.truth_max_chars
    key_facts_max = min(config.key_facts_max, 5)
    key_facts_min = min(config.key_facts_min, key_facts_max)
    return "\n".join(
        [
            "你是海龜湯出題主持人。請產生一題短、明確、可用是／否問答解開的日常型海龜湯。",
            f"所有欄位必須使用 {config.language}，用繁體中文。",
            "",
            "主題忠實度是最高優先：",
            "- 玩家主題中的物品、場景、動作、結果都必須保留，不可替換成相近詞。",
            "- 若主題包含明確結果，例如「報警」「空白發票」「沒有 13 樓」，surface_story 和 truth 都必須直接包含並解釋該結果。",
            "- 不要弱化主題結果，例如不要把「報警」改成只是緊張或警惕。",
            "",
            "故事限制：",
            "- 一個場景、一個異常、一個真相；主要角色最多 2 人。",
            "- 真相必須是普通生活誤會、時間差、視角誤判、物品被整理、標示被誤讀、或日常流程造成。",
            "- 禁止大型陰謀、秘密組織、超自然、未知科技、複雜犯罪、醫療專業、法律專業。",
            "- 除非主題明確提到，禁止使用系統升級、模擬模式、自動警報、駭客、特殊機制解釋。",
            "",
            "欄位要求：",
            f"- surface_story：剛好 2 句，50 到 {surface_story_max_chars} 個中文字；只寫玩家看到的異常結果，不解釋原因。",
            f"- truth：{config.truth_min_chars} 到 {truth_max_chars} 個中文字；必須說明誰、因為什麼、做了什麼、造成什麼結果、玩家為何誤會。",
            f"- key_facts：{key_facts_min} 到 {key_facts_max} 條；必須完整覆蓋真正原因、關鍵行動者、關鍵行動、造成的結果、表面誤導點。",
            "- forbidden_assumptions：2 到 3 條；只能列客觀上不成立的錯誤原因，不可否定主題指定的事實。",
            "- difficulty：固定 medium。",
            "",
            "輸出前自檢，不要輸出自檢文字：",
            "- surface_story 的每個異常是否都能在 truth 和 key_facts 找到直接解釋？",
            "- 正解是否能用一句話說完？",
            "- 是否保留了玩家主題所有明確元素？",
            "- 是否沒有引入不必要的系統、背景或配角？",
            f"內容風格：{config.content_style}。",
        ]
    )


def puzzle_generation_user_prompt(topic: str) -> str:
    return f"玩家提供的主題如下，詳細程度不固定，請合理發想：\n{topic}"


def answer_question_system_prompt() -> str:
    return "\n".join(
        [
            "你是海龜湯主持人。你只做兩步判定：先判斷問題形式是否有效，再判斷答案。",
            "",
            "第一步：is_valid_question",
            "- 問題如果是「嗎／是否／有沒有／是不是／會不會／能不能」這類可用是或否回答的事實問題，必須判定 true。",
            "- 不可以因為答案是 no 而判 invalid。",
            "- 不可以因為問題與真相無關而判 invalid；這種情況 answer 應為 irrelevant。",
            "- 只有要求提示、要求解釋、要求直接說真相、開放式問題、主觀感想問題，才判 false。",
            "",
            "第二步：answer",
            "- 陳述依 truth 為真：yes。",
            "- 陳述依 truth 為假或與 truth 衝突：no。",
            "- 問題形式有效，但問的事實和解開核心真相無關：irrelevant。",
            "- is_valid_question=false 時，answer 必須為 null。",
            "",
            "欄位一致性硬規則：",
            "- answer 是 yes、no 或 irrelevant 時，is_valid_question 必須是 true。",
            "- is_valid_question 是 false 時，answer 必須是 null。",
            "- answer=irrelevant 代表問題形式有效但內容無關；絕對不可搭配 is_valid_question=false。",
            "不要補充說明，不要提示，不要洩漏未被問到的資訊。",
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
            "你是海龜湯遊戲主持人，負責判定玩家提交的完整解答是否已解開謎題。",
            "只回傳 solved 布林值，不提供提示或解釋。",
            "",
            "solved=true 必須同時滿足：",
            "- 玩家說出造成謎面異常的真正原因。",
            "- 玩家說出關鍵行動者做了什麼。",
            "- 玩家說出該行動如何導致謎面中的反常結果。",
            "- 玩家說法沒有和 truth 或 key_facts 的核心事實衝突。",
            "",
            "solved=false 的情況：",
            "- 只猜到不是偷竊、不是超自然、只是誤會等排除性答案。",
            "- 只猜到物品大概位置或角色大概關係，但缺少造成異常的關鍵行動。",
            "- 缺少 key_facts 中任一個必要因果環節。",
            "- 使用錯誤原因解釋，即使部分細節命中。",
            "",
            "判定時以 key_facts 為最低必要門檻；玩家不必逐字相同，但必須完整覆蓋核心因果鏈。",
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
