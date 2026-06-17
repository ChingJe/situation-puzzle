from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from app.config import Settings, get_settings
from app.llm.prompts import (
    answer_question_system_prompt,
    judge_solution_system_prompt,
    puzzle_generation_system_prompt,
    puzzle_generation_user_prompt,
)
from app.models import (
    Puzzle,
    PuzzleDraft,
    QuestionJudgement,
    QuestionRecord,
    SolutionJudgement,
)


OUTPUT_DIR = ROOT_DIR / "docs" / "prompt-tests" / "round1-single-prompt"
RAW_DIR = OUTPUT_DIR / "raw"


@dataclass(frozen=True)
class PromptVariant:
    version: str
    system_prompt: str


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _slug(value: str) -> str:
    normalized = re.sub(r"\s+", "-", value.strip())
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "", normalized)[:60] or "topic"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _chat(settings: Settings, temperature: float) -> ChatOllama:
    return ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=temperature,
        client_kwargs={"timeout": settings.llm.request_timeout_seconds},
    )


def _invoke_structured(
    settings: Settings,
    schema: type[Any],
    messages: list[SystemMessage | HumanMessage],
    temperature: float,
) -> dict[str, Any]:
    model = _chat(settings, temperature).with_structured_output(schema, include_raw=True)
    result = model.invoke(messages)
    parsed = result.get("parsed") if isinstance(result, dict) else result
    raw = result.get("raw") if isinstance(result, dict) else result
    parsing_error = result.get("parsing_error") if isinstance(result, dict) else None
    if parsing_error is not None:
        raise parsing_error
    if not isinstance(parsed, schema):
        parsed = schema.model_validate(parsed)
    return {
        "parsed": parsed.model_dump(mode="json"),
        "raw": _raw_message_payload(raw),
    }


def _raw_message_payload(raw: Any) -> dict[str, Any] | str:
    if hasattr(raw, "model_dump"):
        return raw.model_dump(mode="json")
    return str(raw)


def _generation_variants(settings: Settings) -> dict[str, PromptVariant]:
    v0 = PromptVariant(
        version="generate_puzzle.v0",
        system_prompt=puzzle_generation_system_prompt(settings.puzzle),
    )
    v1 = PromptVariant(
        version="generate_puzzle.v1",
        system_prompt="\n".join(
            [
                "你是海龜湯遊戲的出題主持人，任務是設計一題可以實際遊玩的海龜湯，而不是寫散文或主題評論。",
                f"所有欄位必須使用 {settings.puzzle.language}，用繁體中文。",
                "",
                "海龜湯必備規格：",
                f"1. surface_story 是玩家唯一能看到的謎面，不得超過 {settings.puzzle.surface_story_max_chars} 個中文字。",
                "2. surface_story 必須包含一個明確、反常、值得追問的結果或矛盾，但不能解釋原因。",
                f"3. truth 必須介於 {settings.puzzle.truth_min_chars} 到 {settings.puzzle.truth_max_chars} 個中文字。",
                "4. truth 必須具體交代：角色、做了什麼、為什麼這樣做、事件先後順序、最後結果、謎面的誤導點。",
                "5. truth 必須有唯一主要解答；不能是象徵、夢境、純心理狀態、開放式解讀或沒有結論的氣氛描寫。",
                f"6. key_facts 必須提供 {settings.puzzle.key_facts_min} 到 {settings.puzzle.key_facts_max} 條。",
                "7. 每條 key_facts 都必須是玩家解答需要命中的具體事實，且可以被主持人用是／否問題穩定判定。",
                "8. forbidden_assumptions 放容易被玩家誤以為是真的錯誤假設，例如謎面看似死亡但其實沒有人死亡。",
                "9. difficulty 固定使用 medium，除非題目明顯非常簡單或非常複雜。",
                "",
                "禁止事項：",
                "- 不要輸出抽象評論、主題分析、人生感悟或氣氛總結。",
                "- 不要讓真相只停留在「發生意外」「有秘密」「有人誤會」這種模糊層級。",
                "- 不要需要專業醫療、法律、工程或冷門知識才能解開。",
                "- 避免露骨血腥、歧視、真實個資。",
                "",
                "如果玩家主題很短，請自行補完具體角色、場景與事件，但必須讓謎面與主題明顯相關。",
                f"內容風格：{settings.puzzle.content_style}。",
            ]
        ),
    )
    v2 = PromptVariant(
        version="generate_puzzle.v2",
        system_prompt="\n".join(
            [
                v1.system_prompt,
                "",
                "輸出前請在內部完成自我檢查，不要把檢查內容寫進輸出：",
                "- surface_story 是否只呈現玩家可見的異常結果，且沒有洩漏真相？",
                "- truth 是否有具體角色、行動、原因、順序、結果與誤導點？",
                "- key_facts 是否全都是解答必要事實，而非形容詞、氣氛或主題評論？",
                "- 玩家是否能透過多個是／否問題逐步逼近 truth？",
                "- 玩家提交涵蓋 key_facts 的解答時，主持人是否能明確判定勝利？",
                "若任一項不合格，請在內部重寫題目後，只輸出最終合格版本。",
            ]
        ),
    )
    v3 = PromptVariant(
        version="generate_puzzle.v3",
        system_prompt="\n".join(
            [
                v2.system_prompt,
                "",
                "設計方式要求：",
                "1. 先在內部決定一個「一句話真相」：某角色因某個具體原因做了某個具體行動，導致謎面中的反常結果。",
                "2. 再設計 surface_story，只保留結果、場景與少量可追問線索。",
                "3. key_facts 應覆蓋一句話真相的必要元素：角色身分、關鍵行動、動機／原因、誤導來源、真正結果。",
                "4. 題目不必追求反轉很大，但必須能被問答流程解開。",
            ]
        ),
    )
    v4 = PromptVariant(
        version="generate_puzzle.v4",
        system_prompt="\n".join(
            [
                "你是日常型海龜湯遊戲的出題主持人。你的任務是設計一題可以用是／否問答解開的短篇謎題。",
                f"所有欄位必須使用 {settings.puzzle.language}，用繁體中文。",
                "",
                "核心設計限制：",
                "- 只設計一個主要事件、一個主要誤導點、一個主要真相。",
                "- 主要角色最多 2 人；必要旁觀者最多 1 人。",
                "- 故事必須發生在一般生活場景，可用常識推理。",
                "- 不要大型陰謀、跨國犯罪、超自然、都市傳說、秘密組織、未知科技、專業醫療細節、專業法律細節。",
                "- 不要把真相寫成象徵、心理分析、氣氛描寫或沒有結論的故事。",
                "",
                "欄位要求：",
                f"- surface_story：60 到 {settings.puzzle.surface_story_max_chars} 個中文字，2 到 4 句，只寫玩家看到的異常結果，不解釋原因。",
                f"- truth：{settings.puzzle.truth_min_chars} 到 450 個中文字，必須交代角色、行動、原因、順序、結果、謎面的誤導點。",
                f"- key_facts：{settings.puzzle.key_facts_min} 到 6 條，每條是 15 到 40 字的具體事實，必須可被是／否問題判定。",
                "- forbidden_assumptions：2 到 4 條，列出玩家容易猜錯但不應成立的假設。",
                "- difficulty：除非明顯不適合，固定 medium。",
                "",
                "內部設計流程，不要輸出流程文字：",
                "1. 先想出一句話真相：某人因為某個具體原因做了某個具體行動，造成謎面中的反常結果。",
                "2. 再把這句話拆成 key_facts。",
                "3. 最後寫 surface_story，只留下結果、場景與少量線索。",
                "",
                "合格標準：玩家只要猜到 key_facts 的核心因果，就可以判定解開；如果答案需要猜到太多無關細節，請在內部重寫。",
                f"內容風格：{settings.puzzle.content_style}。",
            ]
        ),
    )
    v5 = PromptVariant(
        version="generate_puzzle.v5",
        system_prompt="\n".join(
            [
                "你是日常型海龜湯遊戲的出題主持人。你要產生短、明確、可玩的謎題，不要寫小說。",
                f"所有欄位必須使用 {settings.puzzle.language}，用繁體中文。",
                "",
                "題目設計必須符合：",
                "- 一個場景、一個反常結果、一個真正原因。",
                "- 主要角色最多 2 人；不要無關配角。",
                "- 真相必須是日常常識能理解的普通誤會、時間差、物品用途誤判、視角誤判或人為整理。",
                "- 玩家正解應該能用一句話說完：某人因為某原因做了某行動，所以造成謎面的反常結果。",
                "- 不要大型陰謀、偷竊集團、超自然、都市傳說、秘密組織、未知科技、醫療專業、法律專業、複雜犯罪。",
                "- 不要使用不合理物理、生硬巧合、抽象心理分析或沒有明確結論的真相。",
                "",
                "欄位格式：",
                "- surface_story：必須是 2 句，50 到 110 個中文字；只呈現玩家看到的異常，不解釋原因。",
                "- truth：220 到 360 個中文字；依序交代角色、原因、行動、結果、誤導點。",
                "- key_facts：4 到 5 條；每條 12 到 35 字；全部都是玩家解答必須命中的具體事實。",
                "- forbidden_assumptions：2 到 3 條；列出常見但錯誤的猜法。",
                "- difficulty：固定 medium。",
                "",
                "輸出前在內部檢查：",
                "- 是否可以用一句話說出正解？",
                "- 是否沒有多餘角色與多層秘密？",
                "- 是否所有 key_facts 都能被是／否問題判定？",
                "- surface_story 是否只有 2 句且沒有說出真相？",
                "若不合格，請在內部重寫後再輸出。",
                "",
                "範例風格，不要照抄：",
                "謎面：便利商店店員明明沒有離開櫃檯，客人卻說他剛剛在門外看見店員。監視器也拍到同一時間櫃檯前確實有人在結帳。",
                "一句話真相：客人把穿著同款制服、來送貨的前店員誤認成正在值班的店員。",
                f"內容風格：{settings.puzzle.content_style}。",
            ]
        ),
    )
    v6 = PromptVariant(
        version="generate_puzzle.v6",
        system_prompt="\n".join(
            [
                v5.system_prompt,
                "",
                "額外硬性規則：",
                "- surface_story 只能有一個主要異常，不要同時放多個不相關線索。",
                "- truth 必須讓讀者能回答：真正原因是什麼、誰做了關鍵行動、何時做的、為什麼謎面會被誤讀。",
                "- key_facts 必須完整覆蓋：真正原因、關鍵行動者、關鍵行動、造成的結果、表面誤導點。",
                "- forbidden_assumptions 必須是客觀上不成立的錯誤事實，不可以寫角色真的產生過的誤會或情緒。",
                "- 不要讓店長、醫師、保安等角色做了關鍵行動卻沒有出現在 key_facts。",
                "- 不要使用「可能」「似乎」「某些」「不經意」來代替具體原因。",
            ]
        ),
    )
    v7 = PromptVariant(
        version="generate_puzzle.v7",
        system_prompt="\n".join(
            [
                v6.system_prompt,
                "",
                "主題遵守規則：",
                "- 玩家主題中的每個明確元素都必須出現在題目中，且不能被換成相近但不同的元素。",
                "- 若主題包含明確結果，例如「報警」「沒有 13 樓」「空白發票」，surface_story 與 truth 都必須直接處理該結果。",
                "- 不要把使用者指定的物品改寫成其他物品，例如不要把空白發票改成收據金額不符。",
                "",
                "一致性規則：",
                "- surface_story 裡每一個異常細節，都必須在 truth 和 key_facts 中有對應解釋。",
                "- truth 不可以新增與 surface_story 無關的系統設定、智慧設備、內部升級、隱藏規定或複雜背景。",
                "- 如果需要制度或規則解釋，必須是一般人能立刻理解的日常規則。",
                "- forbidden_assumptions 不可以否定主題指定的事實；只能否定玩家可能錯猜的原因。",
            ]
        ),
    )
    v8 = PromptVariant(
        version="generate_puzzle.v8",
        system_prompt="\n".join(
            [
                "你是海龜湯出題主持人。請產生一題短、明確、可用是／否問答解開的日常型海龜湯。",
                f"所有欄位必須使用 {settings.puzzle.language}，用繁體中文。",
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
                "- surface_story：剛好 2 句，50 到 120 個中文字；只寫玩家看到的異常結果，不解釋原因。",
                "- truth：200 到 340 個中文字；必須說明誰、因為什麼、做了什麼、造成什麼結果、玩家為何誤會。",
                "- key_facts：4 到 5 條；必須完整覆蓋真正原因、關鍵行動者、關鍵行動、造成的結果、表面誤導點。",
                "- forbidden_assumptions：2 到 3 條；只能列客觀上不成立的錯誤原因，不可否定主題指定的事實。",
                "- difficulty：固定 medium。",
                "",
                "輸出前自檢，不要輸出自檢文字：",
                "- surface_story 的每個異常是否都能在 truth 和 key_facts 找到直接解釋？",
                "- 正解是否能用一句話說完？",
                "- 是否保留了玩家主題所有明確元素？",
                "- 是否沒有引入不必要的系統、背景或配角？",
            ]
        ),
    )
    return {
        variant.version: variant
        for variant in (v0, v1, v2, v3, v4, v5, v6, v7, v8)
    }


def _answer_variants() -> dict[str, PromptVariant]:
    v0 = PromptVariant(
        version="answer_question.v0",
        system_prompt=answer_question_system_prompt(),
    )
    v1 = PromptVariant(
        version="answer_question.v1",
        system_prompt="\n".join(
            [
                "你是海龜湯遊戲主持人，只能根據完整真相與關鍵事實回答玩家問題。",
                "若玩家問題不是可用是／否回答的問題、要求提示、要求解釋、要求開放式資訊，is_valid_question 必須為 false，answer 必須為 null。",
                "若問題有效，answer 只能是 yes、no、irrelevant 三者之一。",
                "yes 表示該問題陳述依 truth 為真；no 表示該問題陳述依 truth 為假；irrelevant 表示該問題與解開核心真相無關或 truth 無法支持判定。",
                "不要補充說明，不要暗示下一步，不要洩漏未被問到的資訊。",
                "遇到措辭含糊但仍可依 truth 判斷的問題，請以最符合 truth 的判斷回答。",
            ]
        ),
    )
    v2 = PromptVariant(
        version="answer_question.v2",
        system_prompt="\n".join(
            [
                "你是海龜湯遊戲主持人，只能根據完整真相與關鍵事實回答玩家問題。",
                "輸出欄位只有 is_valid_question 與 answer，不要補充說明。",
                "",
                "有效問題：",
                "- 只要玩家問的是一個可以用是／否判定的事實陳述，就是有效問題。",
                "- 即使問題的假設是錯的，也仍然是有效問題，answer 應為 no。",
                "- 即使問題和核心真相無關，也仍然是有效問題，answer 應為 irrelevant。",
                "",
                "無效問題：",
                "- 要求提示、要求解釋、要求你直接說出真相。",
                "- 開放式問題，例如「發生了什麼」「在哪裡」「是誰」。",
                "- 要求主觀評價或感受，例如「你覺得可不可怕」。",
                "",
                "answer 規則：",
                "- yes：問題陳述依 truth 為真。",
                "- no：問題陳述依 truth 為假，或與 truth 明確衝突。",
                "- irrelevant：問題是可回答的是非題，但該事實與解開核心真相無關，且 truth 沒有必要支持 yes/no。",
                "- is_valid_question=false 時，answer 必須為 null。",
                "不要暗示下一步，不要洩漏未被問到的資訊。",
            ]
        ),
    )
    v3 = PromptVariant(
        version="answer_question.v3",
        system_prompt="\n".join(
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
                "例子：",
                "- 問：鑰匙掉在床底下了嗎？若 truth 說鑰匙掉在玄關縫隙，回 true/no。",
                "- 問：這件事和晚餐有關嗎？若晚餐與真相無關，回 true/irrelevant。",
                "- 問：請告訴我鑰匙在哪裡。這是要求直接資訊，回 false/null。",
                "不要補充說明，不要提示，不要洩漏未被問到的資訊。",
            ]
        ),
    )
    v4 = PromptVariant(
        version="answer_question.v4",
        system_prompt="\n".join(
            [
                v3.system_prompt,
                "",
                "欄位一致性硬規則：",
                "- answer 是 yes、no 或 irrelevant 時，is_valid_question 必須是 true。",
                "- is_valid_question 是 false 時，answer 必須是 null。",
                "- answer=irrelevant 代表問題形式有效但內容無關；絕對不可搭配 is_valid_question=false。",
                "- 對「X 是真的嗎／X 有發生嗎／X 有關嗎」這種句型，除非 X 是要求提示或主觀感受，必須判 true。",
            ]
        ),
    )
    return {variant.version: variant for variant in (v0, v1, v2, v3, v4)}


def _judge_variants() -> dict[str, PromptVariant]:
    v0 = PromptVariant(
        version="judge_solution.v0",
        system_prompt=judge_solution_system_prompt(),
    )
    v1 = PromptVariant(
        version="judge_solution.v1",
        system_prompt="\n".join(
            [
                "你是海龜湯遊戲主持人，負責判定玩家提交的完整解答是否已抓到核心真相。",
                "只回傳 solved 布林值，不提供提示或解釋。",
                "solved=true 的條件：玩家解答不必逐字相同，但必須涵蓋 key_facts 中足以說明謎面異常的主要角色、關鍵行動、原因、結果與誤導點。",
                "若玩家只猜到主題、氣氛、單一片段，或缺少關鍵因果，必須回傳 solved=false。",
                "若玩家說法與 truth 的核心事實衝突，即使有部分命中，也必須回傳 solved=false。",
            ]
        ),
    )
    v2 = PromptVariant(
        version="judge_solution.v2",
        system_prompt="\n".join(
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
        ),
    )
    return {variant.version: variant for variant in (v0, v1, v2)}


def generate(args: argparse.Namespace) -> None:
    settings = get_settings()
    variants = _generation_variants(settings)
    topics = args.topics
    selected_versions = args.versions or ["generate_puzzle.v0"]
    temperature = (
        args.temperature
        if args.temperature is not None
        else settings.llm.generation_temperature
    )
    for version in selected_versions:
        variant = variants[version]
        for topic in topics:
            start = perf_counter()
            messages = [
                SystemMessage(content=variant.system_prompt),
                HumanMessage(content=puzzle_generation_user_prompt(topic)),
            ]
            status = "ok"
            error: str | None = None
            payload: dict[str, Any]
            try:
                result = _invoke_structured(
                    settings,
                    PuzzleDraft,
                    messages,
                    temperature,
                )
                payload = result["parsed"]
            except Exception as exc:  # noqa: BLE001 - lab tool should preserve raw failure.
                status = "error"
                error = f"{type(exc).__name__}: {exc}"
                payload = {}
            duration_ms = round((perf_counter() - start) * 1000, 2)
            record = {
                "created_at": _now(),
                "task": "generate_puzzle",
                "status": status,
                "error": error,
                "model": settings.ollama_model,
                "base_url": settings.ollama_base_url,
                "temperature": temperature,
                "prompt_version": version,
                "topic": topic,
                "duration_ms": duration_ms,
                "system_prompt": variant.system_prompt,
                "human_prompt": puzzle_generation_user_prompt(topic),
                "output": payload,
            }
            path = RAW_DIR / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{version}_{_slug(topic)}.json"
            _write_json(path, record)
            _append_jsonl(OUTPUT_DIR / "generation-runs.jsonl", record | {"raw_file": str(path.relative_to(ROOT_DIR))})
            print(f"{status} {version} {topic} {duration_ms}ms {path.relative_to(ROOT_DIR)}")


def answer(args: argparse.Namespace) -> None:
    settings = get_settings()
    variants = _answer_variants()
    with Path(args.puzzle_file).open(encoding="utf-8") as file:
        source = json.load(file)
    puzzle = Puzzle(**source["output"] if "output" in source else source)
    history: list[QuestionRecord] = []
    cases = _load_cases(args.cases)
    for version in args.versions or ["answer_question.v1"]:
        variant = variants[version]
        for case in cases:
            question = case["question"]
            start = perf_counter()
            messages = [
                SystemMessage(content=variant.system_prompt),
                HumanMessage(content=_answer_user_prompt(puzzle, question, history)),
            ]
            status = "ok"
            error: str | None = None
            payload: dict[str, Any]
            try:
                result = _invoke_structured(
                    settings,
                    QuestionJudgement,
                    messages,
                    settings.llm.answer_temperature,
                )
                payload = result["parsed"]
            except Exception as exc:  # noqa: BLE001
                status = "error"
                error = f"{type(exc).__name__}: {exc}"
                payload = {}
            record = {
                "created_at": _now(),
                "task": "answer_question",
                "status": status,
                "error": error,
                "model": settings.ollama_model,
                "prompt_version": version,
                "puzzle_file": args.puzzle_file,
                "question": question,
                "expected": case.get("expected"),
                "duration_ms": round((perf_counter() - start) * 1000, 2),
                "system_prompt": variant.system_prompt,
                "output": payload,
            }
            path = RAW_DIR / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{version}_{_slug(question)}.json"
            _write_json(path, record)
            _append_jsonl(OUTPUT_DIR / "answer-runs.jsonl", record | {"raw_file": str(path.relative_to(ROOT_DIR))})
            print(f"{status} {version} {question} -> {payload} {path.relative_to(ROOT_DIR)}")


def judge(args: argparse.Namespace) -> None:
    settings = get_settings()
    variants = _judge_variants()
    with Path(args.puzzle_file).open(encoding="utf-8") as file:
        source = json.load(file)
    puzzle = Puzzle(**source["output"] if "output" in source else source)
    history: list[QuestionRecord] = []
    cases = _load_cases(args.cases)
    for version in args.versions or ["judge_solution.v1"]:
        variant = variants[version]
        for case in cases:
            solution = case["solution"]
            start = perf_counter()
            messages = [
                SystemMessage(content=variant.system_prompt),
                HumanMessage(content=_judge_user_prompt(puzzle, solution, history)),
            ]
            status = "ok"
            error: str | None = None
            payload: dict[str, Any]
            try:
                result = _invoke_structured(
                    settings,
                    SolutionJudgement,
                    messages,
                    settings.llm.judge_temperature,
                )
                payload = result["parsed"]
            except Exception as exc:  # noqa: BLE001
                status = "error"
                error = f"{type(exc).__name__}: {exc}"
                payload = {}
            record = {
                "created_at": _now(),
                "task": "judge_solution",
                "status": status,
                "error": error,
                "model": settings.ollama_model,
                "prompt_version": version,
                "puzzle_file": args.puzzle_file,
                "solution": solution,
                "expected": case.get("expected"),
                "duration_ms": round((perf_counter() - start) * 1000, 2),
                "system_prompt": variant.system_prompt,
                "output": payload,
            }
            path = RAW_DIR / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{version}_{_slug(solution)}.json"
            _write_json(path, record)
            _append_jsonl(OUTPUT_DIR / "judge-runs.jsonl", record | {"raw_file": str(path.relative_to(ROOT_DIR))})
            print(f"{status} {version} {solution[:40]} -> {payload} {path.relative_to(ROOT_DIR)}")


def _load_cases(path: str) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError("Cases file must contain a JSON array.")
    return data


def _answer_user_prompt(
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


def _judge_user_prompt(
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Local prompt testing lab.")
    subparsers = parser.add_subparsers(required=True)

    generate_parser = subparsers.add_parser("generate")
    generate_parser.add_argument("--versions", action="append")
    generate_parser.add_argument("--temperature", type=float)
    generate_parser.add_argument("topics", nargs="+")
    generate_parser.set_defaults(func=generate)

    answer_parser = subparsers.add_parser("answer")
    answer_parser.add_argument("--versions", action="append")
    answer_parser.add_argument("--puzzle-file", required=True)
    answer_parser.add_argument("--cases", required=True)
    answer_parser.set_defaults(func=answer)

    judge_parser = subparsers.add_parser("judge")
    judge_parser.add_argument("--versions", action="append")
    judge_parser.add_argument("--puzzle-file", required=True)
    judge_parser.add_argument("--cases", required=True)
    judge_parser.set_defaults(func=judge)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
