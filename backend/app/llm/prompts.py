from __future__ import annotations

import json

from app.config import PuzzleConfig, PuzzleGenerationConfig
from app.models import (
    CoreTruthDraft,
    Puzzle,
    QuestionRecord,
    SolutionFactsDraft,
    SurfaceStoryDraft,
    TopicInterpretation,
    TruthDraft,
)


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


def interpret_topic_system_prompt(config: PuzzleConfig) -> str:
    return "\n".join(
        [
            "你是海龜湯題目設計的需求解析 agent。",
            f"所有欄位必須使用 {config.language}，用繁體中文。",
            "你的工作只解析玩家主題，不創作完整故事。",
            "",
            "解析規則：",
            "- 保留玩家主題中的場景、物品、角色、動作、明確結果，不可替換成相近詞。",
            "- explicit_results 只放玩家明確指定的結果，例如報警、取消婚禮、東西不見、找不到某樓層。",
            "- hard_constraints 放後續故事絕對不可否定的條件。",
            "- open_space 說明可以合理補充但玩家沒有指定的空白。",
            "- title 要短，適合顯示在歷史紀錄。",
        ]
    )


def interpret_topic_user_prompt(topic: str) -> str:
    return f"玩家主題：\n{topic}"


def generate_core_truth_system_prompt(config: PuzzleConfig) -> str:
    return "\n".join(
        [
            "你是海龜湯核心真相設計 agent。",
            f"所有欄位必須使用 {config.language}，用繁體中文。",
            "你的工作是先產生一個簡單、可被是非問答解開的核心真相，不寫謎面。",
            "",
            "硬性規則：",
            "- 只能有一個主要異常、一條核心因果鏈、最多兩個主要角色。",
            "- 真相必須是普通生活誤會、時間差、視角誤判、物品被整理、標示被誤讀、或日常人物行動造成。",
            "- 核心異常必須是人物行為或明確結果，不可只是商品擺放、補貨、打掃、盤點、陳列或單純看錯。",
            "- 正解不得只是「其實是在正常補貨／打掃／盤點／例行檢查」這類最直覺日常流程。",
            "- 真相必須包含具體關鍵物件或行動條件，讓玩家需要確認至少兩個面向才會接近正解。",
            "- 不得把核心原因寫成標籤貼錯、看錯標示、誤讀文字、以為是試吃區、促銷誤會、商品位置錯誤或單純誤會。",
            "- 真正原因必須是某人有目的的具體行動或具體隱藏條件，不是資訊標示本身錯誤。",
            "- abnormal_result 必須讓玩家追問「這個人為什麼要這樣做？」而不是只追問「他是不是看錯了？」",
            "- 解法至少需要確認兩個面向：行動者做了什麼，以及該行動為何會造成表面異常。",
            "- 可使用輕度日常違規或小型欺瞞，但不可變成複雜犯罪、秘密組織、暗號任務、專業制度或暴力事件。",
            "- 禁止大型陰謀、秘密組織、超自然、未知科技、複雜犯罪、醫療專業、法律專業。",
            "- 除非主題明確提到，禁止使用系統升級、模擬模式、自動警報、駭客、特殊機制。",
            "- 不可否定 topic_interpretation.hard_constraints 或 explicit_results。",
            "- core_truth 必須一到兩句話說完，清楚包含原因、行動者、行動、結果、誤導點。",
            "- 短主題可優先使用：留下收據證明時間地點、買了不拿以製造可見訊號、店員拒賣以阻止明確風險、顧客反覆做同一行動以引起特定人注意。",
            f"內容風格：{config.content_style}。",
        ]
    )


def generate_core_truth_user_prompt(
    topic: str,
    interpretation: TopicInterpretation,
    review_instruction: str | None = None,
) -> str:
    lines = [
        f"玩家主題：{topic}",
        "主題解析：",
        _json_dump(interpretation),
    ]
    if review_instruction:
        lines.extend(["上一輪 reviewer 修正要求：", review_instruction])
    return "\n".join(lines)


def expand_truth_system_prompt(
    puzzle_config: PuzzleConfig,
    generation_config: PuzzleGenerationConfig,
) -> str:
    return "\n".join(
        [
            "你是海龜湯真相擴寫 agent。",
            f"所有欄位必須使用 {puzzle_config.language}，用繁體中文。",
            "你的工作是把 core_truth 擴寫成完整真相，不新增第二條主線或第二個異常。",
            "",
            "擴寫規則：",
            f"- truth 長度控制在 {generation_config.strict_truth_min_chars} 到 {generation_config.strict_truth_max_chars} 個中文字。",
            "- 必須明確說明誰、因為什麼、做了什麼、造成什麼結果、玩家為何會誤會。",
            "- 只能補充讓因果更清楚的日常細節，不得加入新配角、新制度、新機關或新事件解釋。",
            "- 如果謎題涉及角色誤會，truth 要明確區分客觀事實與角色主觀誤判。",
        ]
    )


def expand_truth_user_prompt(
    topic: str,
    interpretation: TopicInterpretation,
    core_truth: CoreTruthDraft,
    review_instruction: str | None = None,
) -> str:
    lines = [
        f"玩家主題：{topic}",
        "主題解析：",
        _json_dump(interpretation),
        "核心真相：",
        _json_dump(core_truth),
    ]
    if review_instruction:
        lines.extend(["上一輪 reviewer 修正要求：", review_instruction])
    return "\n".join(lines)


def extract_solution_facts_system_prompt(config: PuzzleConfig) -> str:
    return "\n".join(
        [
            "你是海龜湯解答事實分層 agent。",
            f"所有欄位必須使用 {config.language}，用繁體中文。",
            "你只能從 core_truth 與 truth 中抽取事實，不得自由新增設定。",
            "",
            "抽取規則：",
            "- required_solution_facts 必須有 2 到 4 條，是玩家通關最低必要門檻。",
            "- required_solution_facts 必須覆蓋真正原因、關鍵行動、造成的反常結果、表面誤導校正。",
            "- supporting_facts 放可支撐問答與完整真相、但玩家提交解答時不必完整重述的背景。",
            "- 不要把純背景、場景常識、過細觀察或可由其他事實推出的內容放入 required_solution_facts。",
            "- 每個 id 必須短且穩定，例如 cause、action、result、misdirection。",
            "- required_solution_facts 優先 2 到 3 條，只有無法涵蓋主要因果時才用 4 條。",
            "- required_solution_facts 只放玩家提交解答必須說出的最低必要事實。",
            "- 表面誤導校正通常放 supporting_facts；只有缺少它會讓答案變成另一個故事時，才放 required_solution_facts。",
            "- 不要把謎面描述、可由原因自然推出的結果、或玩家可忽略的執行細節放入 required_solution_facts。",
        ]
    )


def extract_solution_facts_user_prompt(
    core_truth: CoreTruthDraft,
    truth: TruthDraft,
    review_instruction: str | None = None,
) -> str:
    lines = [
        "核心真相：",
        _json_dump(core_truth),
        "完整真相：",
        _json_dump(truth),
    ]
    if review_instruction:
        lines.extend(["上一輪 reviewer 修正要求：", review_instruction])
    return "\n".join(lines)


def write_surface_story_system_prompt(
    puzzle_config: PuzzleConfig,
    generation_config: PuzzleGenerationConfig,
) -> str:
    return "\n".join(
        [
            "你是海龜湯謎面撰寫 agent。",
            f"所有欄位必須使用 {puzzle_config.language}，用繁體中文。",
            "你的工作只寫玩家看得到的謎面，不可解釋原因。",
            "",
            "硬性規則：",
            f"- surface_story 剛好 2 句，50 到 {generation_config.strict_surface_story_max_chars} 個中文字。",
            "- 只呈現一個主要異常，不要寫兩個互不相關的怪事。",
            "- 謎面中的客觀陳述必須被 truth 承認為客觀事實。",
            "- 如果某件事只是角色誤會，不可寫成客觀事實；必須寫成「他以為...」或「他看到...」。",
            "- 不可出現「其實」「原來」「因為」「真相」等解釋詞。",
            "- 玩家主題明確指定的結果若存在，謎面可以呈現，但不可提前說出原因。",
            "- 不得把角色主觀視角、監視器死角、事後誤判寫成絕對客觀事實。",
            "- 如果 truth 中實際有人或物造成事件，不可寫「全程無人」「完全沒有人」「沒有人靠近」「沒有人碰過」。",
            "- 「憑空消失」「不翼而飛」只能作為角色感受或視角限制，例如「店員回頭時發現...不見」「監視畫面看起來...」。",
            "- 允許使用視角限定詞：看起來、他以為、監視畫面像是、店員回頭時發現、眾人誤以為。",
            "- 不可寫出真正行動者的關鍵行動、完整手法、動機或完整原因。",
            "- 但必須為 required_solution_facts 中的真正原因提供至少一個玩家可觀察的公平線索。",
            "- 公平線索只能是表面現象、痕跡、位置變化、時間關聯或旁人反應，不可直接說出完整真相。",
            "- 例如 truth 是水管破裂時，不可直接寫『水管破裂』，但可以寫『天花板附近有水痕』或『角落地板總是潮濕』。",
            "- 不可直接改寫 required_solution_facts；謎面只能呈現玩家可觀察到的表面矛盾。",
        ]
    )


def write_surface_story_user_prompt(
    topic: str,
    interpretation: TopicInterpretation,
    truth: TruthDraft,
    solution_facts: SolutionFactsDraft,
    review_instruction: str | None = None,
) -> str:
    lines = [
        f"玩家主題：{topic}",
        "主題解析：",
        _json_dump(interpretation),
        "完整真相：",
        _json_dump(truth),
        "解答事實：",
        _json_dump(solution_facts),
    ]
    if review_instruction:
        lines.extend(["上一輪 reviewer 修正要求：", review_instruction])
    return "\n".join(lines)


def generate_assumptions_system_prompt(config: PuzzleConfig) -> str:
    return "\n".join(
        [
            "你是海龜湯誤導與錯誤假設整理 agent。",
            f"所有欄位必須使用 {config.language}，用繁體中文。",
            "請分別列出題目設計用的 misleading_assumptions，以及問答判定用的 forbidden_assumptions。",
            "",
            "規則：",
            "- misleading_assumptions 是玩家容易被謎面引導去猜的方向，2 到 3 條。",
            "- forbidden_assumptions 是客觀上不成立、問答時應否定的假設，2 到 3 條。",
            "- 只能根據 truth、solution_facts、surface_story 產生。",
            "- 不可否定玩家主題指定的事實或謎面客觀事實。",
            "- 每條都要短，不能寫成提示或解答。",
        ]
    )


def generate_assumptions_user_prompt(
    truth: TruthDraft,
    solution_facts: SolutionFactsDraft,
    surface_story: SurfaceStoryDraft,
) -> str:
    return "\n".join(
        [
            "完整真相：",
            _json_dump(truth),
            "解答事實：",
            _json_dump(solution_facts),
            "謎面：",
            _json_dump(surface_story),
        ]
    )


def review_puzzle_system_prompt(config: PuzzleConfig) -> str:
    return "\n".join(
        [
            "你是海龜湯題目一致性審核 agent。你可以看見所有內容。",
            f"所有欄位必須使用 {config.language}，用繁體中文。",
            "請只判斷題目是否適合進入遊戲，並指定最小必要修正節點。",
            "",
            "審核重點：",
            "- 謎面客觀事實不可被 truth 否定。",
            "- surface_story 的每個異常都必須能在 truth 和 required_solution_facts/supporting_facts 找到直接解釋。",
            "- 只能有一個主要異常與一條核心因果鏈。",
            "- required_solution_facts 必須只放通關最低必要事實；supporting_facts 不可被當成硬性通關門檻。",
            "- 低可玩性題目必須打回：正常補貨、正常打掃、盤點、陳列、例行檢查、只是看錯或單純誤會。",
            "- 若核心原因只是標籤貼錯、看錯標示、誤讀文字、以為是試吃區、促銷誤會或商品位置錯誤，必須打回 generate_core_truth。",
            "- 核心異常必須是人物行為或明確結果，不能只是物品擺放或場景狀態。",
            "- 正解必須包含具體關鍵物件或行動條件，玩家需要確認至少兩個面向才會自然接近正解。",
            "- surface_story 不可把視角限制或角色誤判寫成絕對客觀事實，例如全程無人、完全沒有人、沒有人靠近、憑空消失、不翼而飛。",
            "- surface_story 若使用強烈客觀詞，必須有看起來、以為、監視畫面像是、店員回頭時發現等視角限定。",
            "- surface_story 不可洩漏真正行動者的關鍵行動、完整手法、動機或完整原因。",
            "- surface_story 必須讓 required_solution_facts 中的真正原因有至少一個可觀察入口，不能只呈現結果與誤導。",
            "- 可觀察入口可以是表面痕跡、位置變化、時間關聯、異常聲音、旁人反應或物件狀態，但不可直接說出完整真相。",
            "- 若謎面完全沒有線索能導向 required cause，例如真相是水管破裂但謎面沒有水痕、潮濕、天花板、滴水或相關現象，必須打回 write_surface_story。",
            "- 題目要能靠是／否／無關問答逐步解開，不依賴冷僻專業知識。",
            "- 必須保留玩家主題中的明確元素。",
            "",
            "target_node 選擇：",
            "- 核心因果本身不合理或過度發散：generate_core_truth。",
            "- 核心只是標示誤會、商品狀態、店務流程、單純看錯，或缺少有目的的具體行動：generate_core_truth。",
            "- truth 加入第二主線、過長、或和 core_truth 不一致：expand_truth。",
            "- required_solution_facts/supporting_facts 分層錯誤、遺漏或新增 truth 沒有的設定：extract_solution_facts。",
            "- 謎面有客觀事實錯誤、多個異常、未加視角限定的強客觀敘述、暴露完整原因與關鍵行動、或缺少 required cause 的可觀察入口：write_surface_story。",
            "- misleading_assumptions/forbidden_assumptions 否定主題或謎面事實：generate_assumptions。",
            "- 若完全通過，passed=true 且 target_node=finalize_puzzle。",
        ]
    )


def review_puzzle_user_prompt(
    topic: str,
    interpretation: TopicInterpretation,
    core_truth: CoreTruthDraft,
    truth: TruthDraft,
    solution_facts: SolutionFactsDraft,
    surface_story: SurfaceStoryDraft,
    assumptions: object,
) -> str:
    return "\n".join(
        [
            f"玩家主題：{topic}",
            "主題解析：",
            _json_dump(interpretation),
            "核心真相：",
            _json_dump(core_truth),
            "完整真相：",
            _json_dump(truth),
            "解答事實：",
            _json_dump(solution_facts),
            "謎面：",
            _json_dump(surface_story),
            "誤導與錯誤假設：",
            _json_dump(assumptions),
        ]
    )


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
            "- 玩家提交內容本身命中所有 required_solution_facts；或主要內容命中，缺少部分已在既有問答中被明確確認。",
            "- 玩家說法沒有和 truth、required_solution_facts 或 forbidden_assumptions 衝突。",
            "- 玩家必須說出造成謎面異常的真正原因。",
            "- 玩家必須說出關鍵行動者做了什麼。",
            "- 玩家答案已能說明真正原因、關鍵行動、造成的反常結果與表面誤導校正。",
            "",
            "solved=false 的情況：",
            "- 只猜到不是偷竊、不是超自然、只是誤會等排除性答案。",
            "- 只猜到物品大概位置或角色大概關係，但缺少造成異常的關鍵行動。",
            "- 只說出 supporting_facts，沒有命中 required_solution_facts。",
            "- 使用錯誤原因解釋，即使部分細節命中。",
            "",
            "判定時以 required_solution_facts 為最低必要門檻；supporting_facts 只輔助理解，不是硬性通關條件。",
            "請回傳 matched_required_fact_ids、matched_from_history_fact_ids、conflicting_assumptions 與 internal_reason，這些只供內部 log 使用。",
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
            "必要解答事實：",
            *_required_solution_fact_lines(puzzle),
            "支撐事實：",
            *[f"- {fact.id}: {fact.fact}" for fact in puzzle.supporting_facts],
            "不成立假設：",
            *[f"- {item}" for item in puzzle.forbidden_assumptions],
            "既有問答：",
            previous or "（尚無）",
            f"玩家解答：{solution}",
        ]
    )


def _json_dump(value: object) -> str:
    if hasattr(value, "model_dump"):
        return json.dumps(value.model_dump(mode="json"), ensure_ascii=False, indent=2)
    return json.dumps(value, ensure_ascii=False, indent=2)


def _required_solution_fact_lines(puzzle: Puzzle) -> list[str]:
    if puzzle.required_solution_facts:
        return [
            f"- {fact.id} ({fact.role}): {fact.fact}"
            for fact in puzzle.required_solution_facts
        ]
    return [f"- legacy: {fact}" for fact in puzzle.key_facts]
