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
from urllib.request import Request, urlopen

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import Settings, get_settings
from app.llm.prompts import (
    expand_truth_system_prompt,
    expand_truth_user_prompt,
    extract_key_facts_system_prompt,
    extract_key_facts_user_prompt,
    forbidden_assumptions_system_prompt,
    forbidden_assumptions_user_prompt,
    generate_core_truth_system_prompt,
    generate_core_truth_user_prompt,
    interpret_topic_system_prompt,
    interpret_topic_user_prompt,
    review_puzzle_system_prompt,
    review_puzzle_user_prompt,
    write_surface_story_system_prompt,
    write_surface_story_user_prompt,
)
from app.models import (
    CoreTruthDraft,
    ForbiddenAssumptionsDraft,
    KeyFactsDraft,
    PuzzleReviewResult,
    SurfaceStoryDraft,
    TopicInterpretation,
    TruthDraft,
)


OUTPUT_DIR = ROOT_DIR / "docs" / "prompt-tests" / "round2-pipeline-v2"
RAW_DIR = OUTPUT_DIR / "raw"
LAB_PROVIDER = "ollama"
LAB_OPENAI_BASE_URL = "http://localhost:18080/v1"
LAB_OPENAI_MODEL = "qwen3.6-35b-a3b"
LAB_OPENAI_MAX_TOKENS = 1024


@dataclass(frozen=True)
class PromptVariant:
    version: str
    system_prompt: str


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _slug(value: str) -> str:
    normalized = re.sub(r"\s+", "-", value.strip())
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "", normalized)[:80] or "case"


def _dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_dump(item) for item in value]
    if isinstance(value, dict):
        return {key: _dump(item) for key, item in value.items()}
    return value


def _json(value: Any) -> str:
    return json.dumps(_dump(value), ensure_ascii=False, indent=2)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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


def _configure_provider(args: argparse.Namespace) -> None:
    global LAB_OPENAI_BASE_URL, LAB_OPENAI_MAX_TOKENS, LAB_OPENAI_MODEL, LAB_PROVIDER
    LAB_PROVIDER = args.provider
    LAB_OPENAI_BASE_URL = args.openai_base_url
    LAB_OPENAI_MODEL = args.openai_model
    LAB_OPENAI_MAX_TOKENS = args.openai_max_tokens


def _active_model(settings: Settings) -> str:
    return LAB_OPENAI_MODEL if LAB_PROVIDER == "openai-compatible" else settings.ollama_model


def _active_base_url(settings: Settings) -> str:
    return LAB_OPENAI_BASE_URL if LAB_PROVIDER == "openai-compatible" else settings.ollama_base_url


def _invoke_structured(
    settings: Settings,
    task: str,
    schema: type[Any],
    messages: list[SystemMessage | HumanMessage],
    temperature: float,
) -> dict[str, Any]:
    start = perf_counter()
    if LAB_PROVIDER == "openai-compatible":
        return _invoke_openai_compatible_structured(
            settings,
            task,
            schema,
            messages,
            temperature,
            start,
        )
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
        "task": task,
        "duration_ms": round((perf_counter() - start) * 1000, 2),
        "system_prompt": messages[0].content,
        "human_prompt": messages[1].content,
        "parsed": parsed,
        "raw": _dump(raw),
    }


def _invoke_openai_compatible_structured(
    settings: Settings,
    task: str,
    schema: type[Any],
    messages: list[SystemMessage | HumanMessage],
    temperature: float,
    start: float,
) -> dict[str, Any]:
    prompt_messages = [
        {
            "role": "system",
            "content": "\n\n".join(
                [
                    str(messages[0].content),
                    "你必須只輸出 JSON object，不得輸出 Markdown、註解、解釋或其他文字。",
                    "JSON object 必須符合以下 JSON Schema：",
                    json.dumps(schema.model_json_schema(), ensure_ascii=False),
                ]
            ),
        },
        {"role": "user", "content": str(messages[1].content)},
    ]
    payload = {
        "model": LAB_OPENAI_MODEL,
        "messages": prompt_messages,
        "temperature": temperature,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    if LAB_OPENAI_MAX_TOKENS > 0:
        payload["max_tokens"] = LAB_OPENAI_MAX_TOKENS
    request = Request(
        f"{LAB_OPENAI_BASE_URL.rstrip('/')}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=settings.llm.request_timeout_seconds) as response:
        raw_response = json.loads(response.read().decode("utf-8"))
    content = raw_response["choices"][0]["message"].get("content") or ""
    parsed_json = _loads_json_object(content)
    parsed = schema.model_validate(parsed_json)
    return {
        "task": task,
        "duration_ms": round((perf_counter() - start) * 1000, 2),
        "system_prompt": messages[0].content,
        "human_prompt": messages[1].content,
        "parsed": parsed,
        "raw": raw_response,
    }


def _loads_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("Structured output must be a JSON object.")
    return value


def _sentence_count(text: str) -> int:
    parts = [part.strip() for part in re.split(r"[。！？!?]+", text) if part.strip()]
    return len(parts)


def _surface_gate(
    surface_story: str,
    settings: Settings,
) -> dict[str, Any]:
    failed_checks: list[str] = []
    issues: list[str] = []
    text = surface_story.strip()
    sentence_count = _sentence_count(text)
    explanation_match = re.search(r"(?<!實)(其實|原來|因為|真相)", text)
    if not text:
        failed_checks.append("surface_story_empty")
        issues.append("謎面為空")
    if len(text) < 50:
        failed_checks.append("surface_story_too_short")
        issues.append("謎面低於 50 字")
    if len(text) > settings.puzzle_generation.strict_surface_story_max_chars:
        failed_checks.append("surface_story_too_long")
        issues.append("謎面超過字數上限")
    if sentence_count != 2:
        failed_checks.append("surface_story_sentence_count")
        issues.append("謎面不是剛好 2 句")
    if explanation_match:
        failed_checks.append("surface_story_explains_cause")
        issues.append("謎面疑似包含解釋詞")
    if re.search(r"(目的|為了|實則|判斷|需要|驗證|確認步驟|真正原因|背後)", text):
        failed_checks.append("surface_story_leaks_reason")
        issues.append("謎面疑似洩漏目的或判斷")
    if re.search(r"(更奇怪的是|同時|另外|另一方面|隨後|接著|最後)", text):
        failed_checks.append("surface_story_multiple_events")
        issues.append("謎面疑似包含多個事件段落")
    return {
        "passed": not failed_checks,
        "failed_checks": failed_checks,
        "issues": issues,
        "char_count": len(text),
        "sentence_count": sentence_count,
        "contains_explanation_word": bool(explanation_match),
    }


def _truth_gate(truth: str, settings: Settings) -> dict[str, Any]:
    failed_checks: list[str] = []
    if len(truth.strip()) < settings.puzzle_generation.strict_truth_min_chars:
        failed_checks.append("truth_too_short")
    if len(truth.strip()) > settings.puzzle_generation.strict_truth_max_chars:
        failed_checks.append("truth_too_long")
    return {"passed": not failed_checks, "failed_checks": failed_checks, "char_count": len(truth.strip())}


def _full_gate(
    truth: TruthDraft,
    key_facts: KeyFactsDraft,
    surface_story: SurfaceStoryDraft,
    forbidden: ForbiddenAssumptionsDraft,
    settings: Settings,
) -> dict[str, Any]:
    surface = _surface_gate(surface_story.surface_story, settings)
    truth_result = _truth_gate(truth.truth, settings)
    failed_checks = [*surface["failed_checks"], *truth_result["failed_checks"]]
    if not (
        settings.puzzle.key_facts_min
        <= len(key_facts.key_facts)
        <= min(settings.puzzle.key_facts_max, 5)
    ):
        failed_checks.append("key_facts_count")
    if not 2 <= len(forbidden.forbidden_assumptions) <= 3:
        failed_checks.append("forbidden_assumptions_count")
    target_node = "finalize_puzzle"
    if any(check.startswith("truth_") for check in failed_checks):
        target_node = "expand_truth"
    elif "key_facts_count" in failed_checks:
        target_node = "extract_key_facts"
    elif any(check.startswith("surface_") for check in failed_checks):
        target_node = "write_surface_story"
    elif "forbidden_assumptions_count" in failed_checks:
        target_node = "generate_forbidden_assumptions"
    return {
        "passed": not failed_checks,
        "failed_checks": failed_checks,
        "target_node": target_node,
        "surface": surface,
        "truth": truth_result,
    }


def _surface_prompt_variants(settings: Settings) -> dict[str, PromptVariant]:
    base = write_surface_story_system_prompt(settings.puzzle, settings.puzzle_generation)
    v0 = PromptVariant("write_surface_story.v0", base)
    v1 = PromptVariant(
        "write_surface_story.v1",
        "\n".join(
            [
                base,
                "",
                "第二輪測試規則：",
                "- 你只能寫謎面，不可摘要 truth。",
                "- 只寫玩家當下看見或聽見的結果，不寫造成結果的任何原因。",
                "- 不可寫出關鍵行動者做了什麼，也不可寫出標籤、物品、流程被誰改動。",
                "- 如果一句話會回答「為什麼會這樣」，那句話不得出現在謎面。",
            ]
        ),
    )
    v2 = PromptVariant(
        "write_surface_story.v2",
        "\n".join(
            [
                base,
                "",
                "內部流程，不要輸出流程文字：",
                "1. 先從 truth 選出唯一一個玩家可見異常。",
                "2. 丟掉所有原因、背景、行動者動機與完整結論。",
                "3. 第一句只建立普通期待；第二句只呈現與期待相反的可見結果。",
                "4. 最終只輸出這 2 句的 surface_story。",
            ]
        ),
    )
    v3 = PromptVariant(
        "write_surface_story.v3",
        "\n".join(
            [
                base,
                "",
                "反例與正例規則：",
                "- 不要寫「店員誤貼標籤」「店長發現」「顧客被誤導的真正原因」。",
                "- 要寫「顧客照著可見資訊做出選擇，結果和標示或期待不一致」。",
                "- 不要寫「清潔工接電源測試風扇」。",
                "- 要寫「教室燈都關了，風扇卻還在轉」。",
                "- 不要寫「男子每天買便當是為了確認某人」。",
                "- 要寫「男子每天買同一款便當，店員卻選擇報警」。",
            ]
        ),
    )
    v4 = PromptVariant(
        "write_surface_story.v4",
        "\n".join(
            [
                "你是海龜湯謎面撰寫 agent，只負責把完整真相改寫成玩家可見謎面。",
                f"所有欄位必須使用 {settings.puzzle.language}，用繁體中文。",
                "",
                "輸出硬規格：",
                "- surface_story 必須剛好 2 句。",
                f"- 總長度必須 50 到 {settings.puzzle_generation.strict_surface_story_max_chars} 個中文字。",
                "- 第一句句型：角色在主題場景中看到或做了一件普通行為。",
                "- 第二句句型：出現一個與普通期待相反、值得追問的結果。",
                "- 兩句都只能描述玩家可觀察到的事，不得解釋原因。",
                "",
                "禁止：",
                "- 禁止出現「其實」「原來」「因為」「真相」。",
                "- 禁止寫出造成異常的關鍵行動。",
                "- 禁止寫出完整故事流程、後續反應、店長/警察/旁人解釋。",
                "- 禁止同時放入兩個以上異常。",
                "",
                "如果 truth 很複雜，請只挑一個最適合玩家追問的表面矛盾。",
            ]
        ),
    )
    v5 = PromptVariant(
        "write_surface_story.v5",
        "\n".join(
            [
                v4.system_prompt,
                "",
                "輸出前在內部檢查，不要輸出檢查內容：",
                "- 刪掉所有能回答『為什麼』的片段。",
                "- 刪掉所有真正原因、關鍵行動者、修正過程、發現真相的人。",
                "- 確認只剩一個異常結果。",
                "- 確認兩句都不超過玩家當下可見範圍。",
            ]
        ),
    )
    v6 = PromptVariant(
        "write_surface_story.v6",
        "\n".join(
            [
                v5.system_prompt,
                "",
                "來源限制：",
                "- surface_story 只能使用完整真相與關鍵事實中已出現的物品、標示、行動與可見結果。",
                "- 不得新增 truth/key_facts 沒有提到的商品、紙板、批次、位置、人物或第二個異常。",
                "- 不得寫主角心情，例如困惑、疑慮、不安、難以釋懷。",
                "- 不得寫氣氛或聲音，例如低鳴、刺耳、詭異、安靜。",
                "- 第二句必須是客觀可見的反常結果，不是角色主觀感受。",
            ]
        ),
    )
    v7 = PromptVariant(
        "write_surface_story.v7",
        "\n".join(
            [
                "你是海龜湯謎面撰寫 agent，只負責把 truth/key_facts 改寫成玩家可見謎面。",
                f"所有欄位必須使用 {settings.puzzle.language}，用繁體中文。",
                "",
                "最終輸出限制：",
                "- 只填 SurfaceStoryDraft.surface_story 的值。",
                "- surface_story 內只能有 2 句中文句子，不得有換行、Markdown、HTML、XML、註解、自檢文字或括號說明。",
                f"- 總長度必須 50 到 {settings.puzzle_generation.strict_surface_story_max_chars} 個中文字。",
                "- 禁止出現「其實」「原來」「因為」「真相」。",
                "- 禁止出現困惑、疑慮、不安、害怕、難以釋懷、刺耳、低鳴、詭異等情緒或氣氛詞。",
                "",
                "內容來源限制：",
                "- 只能使用 truth/key_facts 已存在的物品、標示、角色、行動與結果。",
                "- 不得新增 truth/key_facts 沒有的商品、紙板、批次、位置、人物、聲音或第二個異常。",
                "- 若某件事只是角色誤會，必須寫成「他以為...」，不可寫成客觀事實。",
                "",
                "兩句模板，必須遵守：",
                "- 第一句：角色在主題場景中根據某個可見資訊做出普通判斷或行動。",
                "- 第二句：一個可見結果和第一句的期待不一致。",
                "",
                "判斷標準：玩家看完謎面應該只知道一個表面矛盾，但不知道任何真正原因。",
            ]
        ),
    )
    v8 = PromptVariant(
        "write_surface_story.v8-contract",
        "\n".join(
            [
                "你是海龜湯謎面撰寫 agent，只負責把完整 truth 壓縮成玩家唯一可見的謎面。",
                f"所有欄位必須使用 {settings.puzzle.language}，用繁體中文。",
                "",
                "責任邊界：",
                "- 只描述玩家可觀察到的表面異常。",
                "- 建立一個普通期待，再呈現與期待不一致的結果。",
                "- 只能使用 truth/key_facts 已存在的角色、物品、行動與結果。",
                "",
                "禁止事項：",
                "- 不得解釋原因、動機、內心或真相。",
                "- 不得新增 truth/key_facts 沒有的線索、人物、物品、位置、聲音或第二個異常。",
                "- 不得輸出內部自檢、Markdown、HTML、XML、註解、括號說明或換行。",
                "- 不得使用「其實」「原來」「因為」「真相」。",
                "- 不得用困惑、疑慮、不安、害怕、難以釋懷、刺耳、低鳴、詭異等情緒或氣氛詞代替客觀異常。",
                "",
                "格式要求：",
                "- 剛好 2 句中文句子。",
                f"- 50 到 {settings.puzzle_generation.strict_surface_story_max_chars} 個中文字。",
                "- 第一句：角色在主題場景中根據某個可見資訊做出普通判斷或行動。",
                "- 第二句：一個可見結果和第一句期待不一致。",
                "",
                "玩家看完謎面只能知道一個表面矛盾，不應知道任何真正原因。",
            ]
        ),
    )
    v9 = PromptVariant(
        "write_surface_story.v9-minimal-contract",
        "\n".join(
            [
                "你只負責寫玩家可見的海龜湯謎面，不解釋真相。",
                f"使用 {settings.puzzle.language}，繁體中文。",
                "",
                "輸出規格：",
                "- 剛好 2 句，50 到 120 個中文字，不換行。",
                "- 第一句只寫普通期待：某人在主題場景中做出一般行動。",
                "- 第二句只寫可見反常：同一人做出和期待不一致的行動或要求。",
                "",
                "絕對禁止出現在 surface_story：",
                "- 其實、原來、因為、真相、目的、為了、實則、判斷、需要、驗證、背後。",
                "- 困惑、疑慮、不安、害怕、詭異、刺耳、低鳴。",
                "- 任何 truth/key_facts 沒有的人物、物品、位置、聲音、第二事件。",
                "",
                "只保留一個表面矛盾。玩家讀完只能問『為什麼這個人要這樣做？』",
            ]
        ),
    )
    return {
        variant.version: variant
        for variant in (v0, v1, v2, v3, v4, v5, v6, v7, v8, v9)
    }


def _core_truth_prompt_variants(settings: Settings) -> dict[str, PromptVariant]:
    base = generate_core_truth_system_prompt(settings.puzzle)
    v0 = PromptVariant("generate_core_truth.v0", base)
    v1 = PromptVariant(
        "generate_core_truth.v1",
        "\n".join(
            [
                base,
                "",
                "第二輪測試規則：",
                "- abnormal_result 必須是玩家聽到後會想問「為什麼會這樣？」的具體表面矛盾。",
                "- 不可把普通的商品擺放、庫存整理、清潔、分類混亂本身當成主要異常。",
                "- 若使用店員整理、標籤、收銀、發票、便當、報警等元素，必須造成一個具體反常行動或結果。",
                "- core_truth 必須能被壓縮成一句正解：某人因某原因做某行動，所以造成謎面異常。",
                "- 不要產生『只是資訊落差』『只是混淆』『讓人感到疑慮』這種沒有遊戲目標的真相。",
            ]
        ),
    )
    v2 = PromptVariant(
        "generate_core_truth.v2",
        "\n".join(
            [
                "你是海龜湯核心真相設計 agent。",
                f"所有欄位必須使用 {settings.puzzle.language}，用繁體中文。",
                "你的工作只設計核心真相，不寫謎面。",
                "",
                "合格題目的核心：",
                "- 必須有一個具體表面異常：某人做了看似不合理的行動、說法或選擇。",
                "- 必須有一個隱藏真相：該行動其實由普通、可理解、日常的原因造成。",
                "- 玩家可以透過是／否問題確認角色、行動、原因、誤導點，最後用一句話解開。",
                "",
                "禁止的弱題材：",
                "- 不要只寫商品擺錯、分類混亂、庫存整理、清潔流程、店內陳列不整齊。",
                "- 不要只寫角色感到困惑、疑慮、不安。",
                "- 不要使用電梯運送人員、系統升級、自動警報、駭客、秘密制度、超自然。",
                "- 不要把核心矛盾寫成抽象的資訊落差，必須落到具體行動與結果。",
                "",
                "可用的日常型反常模式，擇一即可：",
                "- 客人做了看似浪費或多餘的購買，但其實是在傳遞求助訊號。",
                "- 店員做了看似違反服務流程的事，但其實是在避免更大的誤會。",
                "- 發票、標籤或制服造成身分/時間/商品用途的誤判。",
                "- 某人要求報警、退款、丟棄或重買，看似過度，其實有合理原因。",
                "",
                "欄位要求：",
                "- core_truth 一到兩句，包含原因、行動者、關鍵行動、反常結果、誤導點。",
                "- cause 是真正原因，不是『誤會』本身。",
                "- actor_action 是造成謎面異常的具體行動。",
                "- abnormal_result 是玩家可見或可聽見的反常結果。",
                "- misdirection 是玩家最可能猜錯的方向。",
            ]
        ),
    )
    v3 = PromptVariant(
        "generate_core_truth.v3",
        "\n".join(
            [
                "你是海龜湯核心真相設計 agent。",
                f"所有欄位必須使用 {settings.puzzle.language}，用繁體中文。",
                "你的工作只設計一個可玩的核心真相，不寫謎面。",
                "",
                "最高優先規則：核心必須是『人物行為異常』，不是『店內物品狀態異常』。",
                "- abnormal_result 必須描述某個人做了看似不合理的行動、要求、說法或選擇。",
                "- 玩家看見 abnormal_result 後，應該能問：這個人為什麼要這樣做？",
                "- 真正原因必須是日常常識能理解的隱藏動機、身分誤認、時間誤會、求助訊號或證明需求。",
                "",
                "嚴格禁止作為主線：",
                "- 商品擺錯、商品分類、庫存盤點、打包方式、清潔、垃圾回收、陳列位置、促銷標籤、包裝盒。",
                "- 店內某區域看起來奇怪、物品堆積、場景混亂、客人覺得疑惑。",
                "- 處方藥、工業廢料、冷凍櫃電力、專業流程、店內制度、系統警報、秘密規則。",
                "",
                "短主題處理：",
                "- 如果玩家只輸入場景或物品，例如「便利商店」，請自行補一個人物行為異常。",
                "- 不要把短主題補成店務流程問題；必須補成人與人之間可推理的事件。",
                "",
                "可用反常模式，擇一即可：",
                "- 顧客買了商品卻故意不帶走，真正目的是留下可被特定人看到的訊號。",
                "- 顧客每天買同一樣東西，店員因此做出報警或阻止等看似過度的反應。",
                "- 店員拒絕賣出某個普通商品，真正原因是他辨認出商品用途或顧客處境有異。",
                "- 顧客只拿發票或收據不要商品，真正原因是需要時間、地點或身分證明。",
                "- 某人看見同一個店員同時出現在兩處，真正原因是制服、倒影或身分誤認。",
                "",
                "欄位要求：",
                "- core_truth 一到兩句，必須包含：誰、為什麼、做了什麼、造成玩家看到的反常結果、玩家會誤會什麼。",
                "- cause 必須是隱藏原因，不可只寫『誤會』或『資訊落差』。",
                "- actor_action 必須是具體人物行動。",
                "- abnormal_result 必須是可放進謎面的表面異常，且不得是物品擺放或場景混亂。",
                "- misdirection 必須指出玩家會猜錯的方向。",
            ]
        ),
    )
    v4 = PromptVariant(
        "generate_core_truth.v4-contract",
        "\n".join(
            [
                "你是海龜湯核心真相設計 agent。這是整個 pipeline 最重要的節點。",
                f"所有欄位必須使用 {settings.puzzle.language}，用繁體中文。",
                "你的工作只產生可玩的核心謎題骨架，不寫完整真相，不寫玩家可見謎面。",
                "",
                "可玩性硬規則：",
                "- 必須產生一條核心因果鏈：某人因為 X 做了 Y，導致玩家看到 Z，但玩家誤以為 W。",
                "- abnormal_result 必須是玩家可見或可聽見的『人物行為異常』，例如某人做了看似不合理的行動、要求、說法或選擇。",
                "- 玩家看見 abnormal_result 後，應能追問：這個人為什麼要這樣做？",
                "- cause 必須是真正原因，不可只寫『誤會』『資訊落差』『保護性行為』等抽象詞。",
                "- actor_action 必須是具體人物行動。",
                "",
                "主要禁止方向：",
                "- 不得把商品擺放、商品分類、庫存盤點、打包方式、清潔、垃圾回收、陳列位置、促銷標籤、包裝盒作為主線。",
                "- 不得讓角色只是困惑、疑慮、不安，卻沒有客觀反常行動或結果。",
                "- 不得使用秘密組織、接頭、任務暗號、犯罪集團、專業流程、內部制度。",
                "- 不得使用系統警報、自動偵測、駭客、模擬模式、未知科技、超自然作為解法。",
                "",
                "短主題處理：",
                "- 如果玩家只輸入場景或物品，例如「便利商店」，請保留場景並補一個日常人物行為異常。",
                "- 補充內容不得蓋過場景本身，不得變成店務流程或物品狀態問題。",
                "",
                "可用方向，擇一即可，並保持日常：",
                "- 顧客買了商品卻故意不帶走，真正目的是讓家人、朋友、同事或店員看見某個日常訊號。",
                "- 店員拒絕賣出普通商品，真正原因是他辨認出顧客的處境或用途有異。",
                "- 某人只拿收據或發票不要商品，真正原因是需要時間、地點或身分證明。",
                "- 某人反覆買同一樣東西，使店員做出看似過度但合理的反應。",
                "- 某人要求退款、報警、丟棄或重買，看似不合理，其實是為了避免日常誤會或證明某件事。",
                "",
                "欄位要求：",
                "- core_truth 一到兩句，包含真正原因、關鍵行動者、關鍵行動、表面異常、誤導點。",
                "- abnormal_result 可直接成為謎面核心，不得是物品擺放、場景混亂或心理狀態。",
                "- misdirection 必須指出玩家最可能猜錯的方向。",
            ]
        ),
    )
    v5 = PromptVariant(
        "generate_core_truth.v5-contract",
        "\n".join(
            [
                v4.system_prompt,
                "",
                "第三輪收斂規則：",
                "- 真正原因必須是人際關係或日常需求，例如家人擔心、朋友求助、店員辨認顧客狀態、需要證明時間/地點/身分。",
                "- 不得使用食品安全、過敏原、品質檢查、商品召回、批次號碼、印刷瑕疵、檢測人員、專業資格或任何商品專業知識。",
                "- 不得把店員設定成隱藏專業人員；店員只能是普通店員，顧客也只能是普通顧客。",
                "- 若使用『訊號』，只能是日常可理解的提醒或求助，例如固定購買、留下收據、不要商品、重複一句話；不得依賴暗號、組織、批次、標記或專業辨識。",
                "- 優先讓異常落在人的選擇：拒賣、報警、只拿收據、買了不拿、要求重買、要求退款、請顧客留下。",
            ]
        ),
    )
    v6 = PromptVariant(
        "generate_core_truth.v6-minimal-contract",
        "\n".join(
            [
                "你是海龜湯核心真相設計 agent。只設計核心，不寫謎面。",
                f"使用 {settings.puzzle.language}，繁體中文。",
                "",
                "必須輸出一個日常、人際、可用是非問答解開的核心：",
                "- 某人因為 X 做了 Y，導致玩家看到 Z，但玩家誤以為 W。",
                "- Z 必須是人物行為異常：拒賣、報警、買了不拿、只拿收據、要求重買、要求顧客留下、說出奇怪要求。",
                "- X 必須是普通生活理由：求助、保護家人朋友、避免誤會、證明時間地點、認出熟人處境。",
                "",
                "禁止使用這些主線或詞意：",
                "- 商品擺放、分類、庫存、打包、清潔、垃圾、陳列、促銷。",
                "- 專業、流程、制度、身份驗證、狀態驗證、批次、標籤、印刷、檢測、過敏原、污染、召回。",
                "- 秘密組織、接頭、任務、暗號、犯罪集團、駭客、系統、超自然。",
                "- 角色只是困惑或不安，沒有可見行動異常。",
                "",
                "欄位長度：",
                "- core_truth 最多 80 個中文字。",
                "- cause、actor_action、abnormal_result、misdirection 各最多 45 個中文字。",
                "- 每欄都要具體，不要寫抽象詞。",
            ]
        ),
    )
    v7 = PromptVariant(
        "generate_core_truth.v7-concrete-contract",
        "\n".join(
            [
                "你是海龜湯核心真相設計 agent。只設計核心，不寫謎面。",
                f"使用 {settings.puzzle.language}，繁體中文。",
                "",
                "輸出必須是一個具體日常事件：",
                "- 公式：某人因為具體原因 X，做了具體行動 Y，導致可見異常 Z，玩家誤以為 W。",
                "- X 必須能用一句生活常識理解，且要說出人與人的關係或具體需求。",
                "- Z 必須是人物行為異常：拒賣、報警、買了不拿、只拿收據、要求重買、要求顧客留下、說出奇怪要求。",
                "",
                "禁止抽象與不可判定寫法：",
                "- 禁止使用：某個、某項、特殊、私密、保密、身份、狀態、驗證、流程、標準、內部、專業。",
                "- 禁止使用：商品擺放、分類、庫存、打包、清潔、垃圾、陳列、促銷、批次、標籤、印刷、檢測、過敏原、召回。",
                "- 禁止使用：秘密組織、接頭、任務、暗號、犯罪集團、駭客、系統、超自然。",
                "",
                "可用具體模式，擇一改寫到玩家主題：",
                "- 顧客買了商品卻故意不帶走，因為要讓同行者以為他真的進店買東西。",
                "- 店員報警，因為顧客每天買同一份餐點但收件人其實失蹤。",
                "- 顧客只拿收據不要商品，因為要向家人證明自己某時某地在店裡。",
                "- 店員拒賣普通商品，因為他認出顧客是在被迫購買不需要的東西。",
                "",
                "欄位長度：",
                "- core_truth 最多 80 個中文字。",
                "- cause、actor_action、abnormal_result、misdirection 各最多 45 個中文字。",
                "- 每欄都要具體，不要寫抽象詞。",
            ]
        ),
    )
    return {variant.version: variant for variant in (v0, v1, v2, v3, v4, v5, v6, v7)}


def _interpret_topic_prompt_variants(settings: Settings) -> dict[str, PromptVariant]:
    base = interpret_topic_system_prompt(settings.puzzle)
    v0 = PromptVariant("interpret_topic.v0", base)
    v1 = PromptVariant(
        "interpret_topic.v1-contract",
        "\n".join(
            [
                "你是海龜湯題目設計的需求解析 agent。",
                f"所有欄位必須使用 {settings.puzzle.language}，用繁體中文。",
                "你的工作只解析玩家主題，不創作真相、不補完整故事、不決定核心反轉。",
                "",
                "解析規則：",
                "- 保留玩家主題中的場景、物品、角色、動作、明確結果，不可替換成相近詞。",
                "- explicit_results 只放玩家明確指定的結果，例如報警、取消婚禮、東西不見、找不到某樓層。",
                "- hard_constraints 放後續故事絕對不可否定的條件；不得輸出空字串。",
                "- open_space 只描述可自由補充的範圍，不要鼓勵店務流程、商品擺放、庫存、清潔、陳列或專業制度。",
                "- 若 topic 很短，只標記為開放場景，提醒後續可補一個日常人物行為異常。",
                "- title 要短，適合顯示在歷史紀錄。",
            ]
        ),
    )
    v2 = PromptVariant(
        "interpret_topic.v2-minimal-contract",
        "\n".join(
            [
                "你只解析玩家主題，不創作故事。",
                f"使用 {settings.puzzle.language}，繁體中文。",
                "- 保留明確場景、物品、角色、動作、結果。",
                "- hard_constraints 不得有空字串；短主題至少寫：故事主要場景必須是該主題。",
                "- open_space 對短主題只寫：可補一個日常人物行為異常。",
                "- 不要建議商品擺放、店務流程、庫存、清潔、陳列、專業制度。",
            ]
        ),
    )
    v3 = PromptVariant(
        "interpret_topic.v3-short-topic-contract",
        "\n".join(
            [
                "你只解析玩家主題，不創作故事。",
                f"使用 {settings.puzzle.language}，繁體中文。",
                "",
                "嚴格規則：",
                "- objects 只能放玩家文字中明確出現的物品。",
                "- actors 只能放玩家文字中明確出現的人物。",
                "- explicit_results 只能放玩家文字中明確出現的結果。",
                "- hard_constraints 不得有空字串；只放玩家明確指定、後續不可否定的條件。",
                "- open_space 只能描述可補充範圍，不得加入角色、物品、事件、硬限制。",
                "",
                "短主題規則：",
                "- 若玩家只輸入單一場景或物品，例如「便利商店」，objects=[], actors=[], explicit_results=[]。",
                "- 這類短主題的 hard_constraints 只寫：故事主要場景必須是便利商店。",
                "- 這類短主題的 open_space 只寫：可補一個日常人物行為異常，但不得把主線寫成店務流程或商品狀態。",
            ]
        ),
    )
    return {variant.version: variant for variant in (v0, v1, v2, v3)}


def _expand_truth_prompt_variants(settings: Settings) -> dict[str, PromptVariant]:
    base = expand_truth_system_prompt(settings.puzzle, settings.puzzle_generation)
    v0 = PromptVariant("expand_truth.v0", base)
    v1 = PromptVariant(
        "expand_truth.v1-contract",
        "\n".join(
            [
                "你是海龜湯真相擴寫 agent，只負責把 core_truth 擴寫成完整、可供問答與解答判定使用的 truth。",
                f"所有欄位必須使用 {settings.puzzle.language}，用繁體中文。",
                "",
                "責任邊界：",
                "- 必須保留 core_truth 的同一條因果鏈。",
                "- 必須補足誰、為什麼、做了什麼、造成什麼反常結果、玩家為什麼容易誤會。",
                "- 只能補充讓因果更清楚的日常細節。",
                "",
                "禁止事項：",
                "- 不得新增第二主線、第二個異常或小說式背景。",
                "- 不得新增 core_truth 沒有的秘密組織、任務、暗號、犯罪集團、制度、設備或外部角色群。",
                "- 不得改寫 core_truth 的真正原因。",
                "- 不得用『資訊落差』『誤會』等抽象詞代替具體因果。",
                "",
                "長度要求：",
                f"- truth 必須落在 {settings.puzzle_generation.strict_truth_min_chars} 到 {settings.puzzle_generation.strict_truth_max_chars} 個中文字。",
                "- 目標是 160 到 260 個中文字，不要貼近上限。",
            ]
        ),
    )
    v2 = PromptVariant(
        "expand_truth.v2-minimal-contract",
        "\n".join(
            [
                "你是海龜湯真相擴寫 agent，只把 core_truth 擴成一段 truth。",
                f"使用 {settings.puzzle.language}，繁體中文。",
                "",
                "規則：",
                "- 只保留 core_truth 的同一條因果鏈，不新增第二事件。",
                "- 依序寫清楚：誰、真正原因、具體行動、造成的反常結果、玩家容易誤會什麼。",
                "- 只補日常細節，不補專業背景。",
                "- 160 到 230 個中文字。",
                "",
                "禁止使用：專業、流程、制度、身份驗證、狀態驗證、批次、標籤、印刷、檢測、過敏原、污染、召回、秘密組織、任務、暗號。",
            ]
        ),
    )
    v3 = PromptVariant(
        "expand_truth.v3-concrete-contract",
        "\n".join(
            [
                "你是海龜湯真相擴寫 agent，只把 core_truth 擴成一段 truth。",
                f"使用 {settings.puzzle.language}，繁體中文。",
                "",
                "規則：",
                "- 只保留 core_truth 的同一條因果鏈，不新增第二事件。",
                "- 依序寫清楚：誰、真正原因、具體行動、造成的反常結果、玩家容易誤會什麼。",
                "- 160 到 230 個中文字。",
                "",
                "禁止：",
                "- 不得新增 core_truth 沒有的人物群、制度、設備、任務或背景。",
                "- 不得使用抽象詞代替因果：某個、某項、特殊、私密、保密、身份、狀態、驗證、流程、標準、內部、專業。",
                "- 不得使用專業或商品流程：批次、標籤、印刷、檢測、過敏原、召回、庫存、清潔、陳列、促銷。",
            ]
        ),
    )
    return {variant.version: variant for variant in (v0, v1, v2, v3)}


def _review_prompt_variants(settings: Settings) -> dict[str, PromptVariant]:
    base = review_puzzle_system_prompt(settings.puzzle)
    v0 = PromptVariant("review_puzzle.v0", base)
    v1 = PromptVariant(
        "review_puzzle.v1-contract",
        "\n".join(
            [
                "你是海龜湯題目審核 agent，可以看見所有內容。",
                f"所有欄位必須使用 {settings.puzzle.language}，用繁體中文。",
                "請只判斷題目是否適合進入遊戲，並指定最小必要修正節點；不得直接重寫題目或創作新設定。",
                "",
                "一致性審核：",
                "- surface_story 的每個異常都必須能在 truth/key_facts 找到根據。",
                "- surface_story 不得新增 truth/key_facts 沒有的線索。",
                "- key_facts 都必須來自 truth。",
                "- forbidden_assumptions 不得否定 topic、truth 或 surface_story 的客觀事實。",
                "",
                "可玩性審核：",
                "- 核心異常必須是人物行為異常，或至少是明確可追問的反常結果。",
                "- 若主線只是商品擺放、打包、庫存、清潔、陳列、垃圾分類或物品狀態，必須打回 generate_core_truth。",
                "- 若角色只是困惑、疑慮、不安，沒有客觀反常結果，必須打回 write_surface_story 或 generate_core_truth。",
                "- 玩家必須能透過是非問答逐步確認角色、行動、原因、結果與誤導點。",
                "- 正解必須能用一句話概括。",
                "",
                "可判定性審核：",
                "- truth 必須足以回答常見 yes/no/irrelevant 問題。",
                "- key_facts 必須覆蓋勝負判定必要因果。",
                "- 題目不得依賴冷門專業知識、任意猜測、秘密組織、任務暗號、超自然或未知科技。",
                "",
                "target_node 選擇：",
                "- 核心不可玩、主線是店務流程/物品狀態、使用秘密組織/任務/專業流程、多條核心因果鏈：generate_core_truth。",
                "- core truth 合理但 truth 新增第二主線、過長、過度戲劇化、與 core truth 不一致：expand_truth。",
                "- key facts 遺漏核心因果、新增設定或條數不符：extract_key_facts。",
                "- 謎面格式不符、洩漏原因、新增線索、只有情緒氣氛沒有客觀異常：write_surface_story。",
                "- forbidden assumptions 條數不符或否定 topic/surface story 客觀事實：generate_forbidden_assumptions。",
                "- 完全通過：passed=true 且 target_node=finalize_puzzle。",
                "",
                "revision_instruction 必須具體包含失敗原因、要保留什麼、要移除或避免什麼、修正後目標形態。",
                "如果 passed=false，issues 不得為空。",
            ]
        ),
    )
    return {variant.version: variant for variant in (v0, v1)}


def _surface_human_prompt(
    topic: str,
    interpretation: TopicInterpretation,
    truth: TruthDraft,
    key_facts: KeyFactsDraft,
    review_instruction: str | None = None,
) -> str:
    return write_surface_story_user_prompt(
        topic,
        interpretation,
        truth,
        key_facts,
        review_instruction,
    )


def run_baseline(args: argparse.Namespace) -> None:
    _configure_provider(args)
    settings = get_settings()
    _apply_runtime_overrides(settings, args)
    interpret_variant = _interpret_topic_prompt_variants(settings)[args.interpret_version]
    surface_variant = _surface_prompt_variants(settings)[args.surface_version]
    core_variant = _core_truth_prompt_variants(settings)[args.core_version]
    expand_variant = _expand_truth_prompt_variants(settings)[args.expand_version]
    review_variant = _review_prompt_variants(settings)[args.review_version]
    for index in range(args.runs):
        record = _run_pipeline_once(
            settings,
            args.topic,
            index,
            interpret_variant,
            core_variant,
            expand_variant,
            surface_variant,
            review_variant,
        )
        raw_path = (
            RAW_DIR
            / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_pipeline_{interpret_variant.version}_{core_variant.version}_{expand_variant.version}_{surface_variant.version}_{review_variant.version}_{_slug(args.topic)}_{index + 1}.json"
        )
        _write_json(raw_path, record)
        _append_jsonl(OUTPUT_DIR / "baseline-runs.jsonl", record | {"raw_file": str(raw_path.relative_to(ROOT_DIR))})
        print(
            f"{record['status']} {surface_variant.version} {index + 1}/{args.runs} "
            f"interpret={interpret_variant.version} core={core_variant.version} expand={expand_variant.version} review={review_variant.version} "
            f"target={record.get('final_target_node')} checks={record.get('final_failed_checks')} "
            f"{record['duration_ms']}ms {raw_path.relative_to(ROOT_DIR)}"
        )


def _run_pipeline_once(
    settings: Settings,
    topic: str,
    run_index: int,
    interpret_variant: PromptVariant,
    core_variant: PromptVariant,
    expand_variant: PromptVariant,
    surface_variant: PromptVariant,
    review_variant: PromptVariant,
) -> dict[str, Any]:
    start = perf_counter()
    nodes: list[dict[str, Any]] = []
    revision_count = 0
    review_instruction: str | None = None
    status = "ok"
    error: str | None = None
    final_gate: dict[str, Any] | None = None
    final_review: dict[str, Any] | None = None

    try:
        interpretation_call = _invoke_structured(
            settings,
            "interpret_topic",
            TopicInterpretation,
            [
                SystemMessage(content=interpret_variant.system_prompt),
                HumanMessage(content=interpret_topic_user_prompt(topic)),
            ],
            settings.llm.generation_temperature,
        )
        interpretation = interpretation_call["parsed"]
        nodes.append(_node_record(interpretation_call))

        core_call = _invoke_structured(
            settings,
            "generate_core_truth",
            CoreTruthDraft,
            [
                SystemMessage(content=core_variant.system_prompt),
                HumanMessage(content=generate_core_truth_user_prompt(topic, interpretation)),
            ],
            settings.llm.generation_temperature,
        )
        core_truth = core_call["parsed"]
        nodes.append(_node_record(core_call))

        truth_call = _invoke_structured(
            settings,
            "expand_truth",
            TruthDraft,
            [
                SystemMessage(content=expand_variant.system_prompt),
                HumanMessage(content=expand_truth_user_prompt(topic, interpretation, core_truth)),
            ],
            settings.llm.generation_temperature,
        )
        truth = truth_call["parsed"]
        nodes.append(_node_record(truth_call))

        key_facts_call = _invoke_structured(
            settings,
            "extract_key_facts",
            KeyFactsDraft,
            [
                SystemMessage(content=extract_key_facts_system_prompt(settings.puzzle)),
                HumanMessage(content=extract_key_facts_user_prompt(truth)),
            ],
            settings.llm.generation_temperature,
        )
        key_facts = key_facts_call["parsed"]
        nodes.append(_node_record(key_facts_call))

        while True:
            surface_call = _invoke_structured(
                settings,
                "write_surface_story",
                SurfaceStoryDraft,
                [
                    SystemMessage(content=surface_variant.system_prompt),
                    HumanMessage(
                        content=write_surface_story_user_prompt(
                            topic,
                            interpretation,
                            truth,
                            key_facts,
                            review_instruction,
                        )
                    ),
                ],
                settings.llm.generation_temperature,
            )
            surface = surface_call["parsed"]
            nodes.append(_node_record(surface_call, revision_count=revision_count))

            forbidden_call = _invoke_structured(
                settings,
                "generate_forbidden_assumptions",
                ForbiddenAssumptionsDraft,
                [
                    SystemMessage(content=forbidden_assumptions_system_prompt(settings.puzzle)),
                    HumanMessage(content=forbidden_assumptions_user_prompt(truth, key_facts, surface)),
                ],
                settings.llm.generation_temperature,
            )
            forbidden = forbidden_call["parsed"]
            nodes.append(_node_record(forbidden_call, revision_count=revision_count))

            gate = _full_gate(truth, key_facts, surface, forbidden, settings)
            final_gate = gate
            if not gate["passed"]:
                review_instruction = "；".join(gate["surface"]["issues"]) or "請修正 deterministic gate 標記的問題"
                final_review = {
                    "source": "deterministic_gate",
                    "passed": False,
                    "target_node": gate["target_node"],
                    "issues": gate["failed_checks"],
                    "revision_instruction": review_instruction,
                }
            else:
                review_call = _invoke_structured(
                    settings,
                    "review_puzzle",
                    PuzzleReviewResult,
                    [
                        SystemMessage(content=review_variant.system_prompt),
                        HumanMessage(
                            content=review_puzzle_user_prompt(
                                topic,
                                interpretation,
                                core_truth,
                                truth,
                                key_facts,
                                surface,
                                forbidden.forbidden_assumptions,
                            )
                        ),
                    ],
                    settings.llm.judge_temperature,
                )
                review = review_call["parsed"]
                nodes.append(_node_record(review_call, revision_count=revision_count))
                final_review = {"source": "llm_reviewer", **review.model_dump(mode="json")}
                if not review.passed:
                    review_instruction = review.revision_instruction

            if final_review and final_review["passed"]:
                break
            if revision_count >= settings.puzzle_generation.max_revision_rounds:
                status = "revision_exhausted"
                break
            if final_review and final_review["target_node"] != "write_surface_story":
                status = "needs_non_surface_revision"
                break
            revision_count += 1
    except Exception as exc:  # noqa: BLE001 - lab must preserve failures.
        status = "error"
        error = f"{type(exc).__name__}: {exc}"

    return {
        "created_at": _now(),
        "task": "pipeline_baseline" if surface_variant.version == "write_surface_story.v0" else "pipeline_candidate",
        "status": status,
        "error": error,
        "provider": LAB_PROVIDER,
        "model": _active_model(settings),
        "base_url": _active_base_url(settings),
        "interpret_prompt_version": interpret_variant.version,
        "core_prompt_version": core_variant.version,
        "expand_prompt_version": expand_variant.version,
        "surface_prompt_version": surface_variant.version,
        "review_prompt_version": review_variant.version,
        "topic": topic,
        "run_index": run_index,
        "duration_ms": round((perf_counter() - start) * 1000, 2),
        "revision_count": revision_count,
        "final_target_node": (final_review or {}).get("target_node"),
        "final_failed_checks": (final_gate or {}).get("failed_checks"),
        "final_gate": final_gate,
        "final_review": final_review,
        "nodes": nodes,
    }


def _node_record(call: dict[str, Any], revision_count: int = 0) -> dict[str, Any]:
    return {
        "task": call["task"],
        "revision_count": revision_count,
        "duration_ms": call["duration_ms"],
        "system_prompt": call["system_prompt"],
        "human_prompt": call["human_prompt"],
        "parsed": _dump(call["parsed"]),
        "raw": call["raw"],
    }


def run_surface(args: argparse.Namespace) -> None:
    _configure_provider(args)
    settings = get_settings()
    _apply_runtime_overrides(settings, args)
    variants = _surface_prompt_variants(settings)
    selected_versions = args.versions or ["write_surface_story.v0"]
    cases = _load_surface_cases(args.baseline_file, args.limit)
    for case_index, case in enumerate(cases):
        for version in selected_versions:
            variant = variants[version]
            for repeat_index in range(args.repeats):
                record = _run_surface_once(
                    settings,
                    case,
                    case_index,
                    repeat_index,
                    variant,
                )
                raw_path = (
                    RAW_DIR
                    / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{version}_{case_index + 1}_{repeat_index + 1}.json"
                )
                _write_json(raw_path, record)
                _append_jsonl(OUTPUT_DIR / "surface-runs.jsonl", record | {"raw_file": str(raw_path.relative_to(ROOT_DIR))})
                gate = record["gate"]
                print(
                    f"{record['status']} {version} case={case_index + 1} repeat={repeat_index + 1} "
                    f"pass={gate['passed']} checks={gate['failed_checks']} "
                    f"chars={gate['char_count']} sentences={gate['sentence_count']} "
                    f"{record['duration_ms']}ms"
                )


def _load_surface_cases(path: str, limit: int | None) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            run = json.loads(line)
            parsed_by_task = {
                node["task"]: node["parsed"]
                for node in run.get("nodes", [])
                if node.get("task") in {"interpret_topic", "expand_truth", "extract_key_facts"}
            }
            if {"interpret_topic", "expand_truth", "extract_key_facts"} <= parsed_by_task.keys():
                cases.append(
                    {
                        "topic": run["topic"],
                        "source_run_index": run["run_index"],
                        "interpretation": parsed_by_task["interpret_topic"],
                        "truth": parsed_by_task["expand_truth"],
                        "key_facts": parsed_by_task["extract_key_facts"],
                    }
                )
            if limit and len(cases) >= limit:
                break
    if not cases:
        raise ValueError("No usable surface cases found in baseline file.")
    return cases


def _run_surface_once(
    settings: Settings,
    case: dict[str, Any],
    case_index: int,
    repeat_index: int,
    variant: PromptVariant,
) -> dict[str, Any]:
    start = perf_counter()
    status = "ok"
    error: str | None = None
    payload: dict[str, Any] = {}
    gate: dict[str, Any] = {
        "passed": False,
        "failed_checks": ["not_run"],
        "char_count": 0,
        "sentence_count": 0,
    }
    interpretation = TopicInterpretation.model_validate(case["interpretation"])
    truth = TruthDraft.model_validate(case["truth"])
    key_facts = KeyFactsDraft.model_validate(case["key_facts"])
    human_prompt = _surface_human_prompt(case["topic"], interpretation, truth, key_facts)
    try:
        result = _invoke_structured(
            settings,
            "write_surface_story",
            SurfaceStoryDraft,
            [
                SystemMessage(content=variant.system_prompt),
                HumanMessage(content=human_prompt),
            ],
            settings.llm.generation_temperature,
        )
        output = result["parsed"]
        payload = output.model_dump(mode="json")
        gate = _surface_gate(output.surface_story, settings)
        raw = result["raw"]
    except Exception as exc:  # noqa: BLE001
        status = "error"
        error = f"{type(exc).__name__}: {exc}"
        raw = {}
    return {
        "created_at": _now(),
        "task": "write_surface_story_candidate",
        "status": status,
        "error": error,
        "provider": LAB_PROVIDER,
        "model": _active_model(settings),
        "base_url": _active_base_url(settings),
        "prompt_version": variant.version,
        "case_index": case_index,
        "source_run_index": case["source_run_index"],
        "repeat_index": repeat_index,
        "duration_ms": round((perf_counter() - start) * 1000, 2),
        "topic": case["topic"],
        "system_prompt": variant.system_prompt,
        "human_prompt": human_prompt,
        "output": payload,
        "raw": raw,
        "gate": gate,
    }


def summarize(args: argparse.Namespace) -> None:
    surface_path = OUTPUT_DIR / "surface-runs.jsonl"
    baseline_path = OUTPUT_DIR / "baseline-runs.jsonl"
    lines: list[str] = [
        "# Pipeline v2 Prompt 測試摘要",
        "",
        f"更新時間：{_now()}",
        "",
    ]
    if baseline_path.exists():
        baseline = _read_jsonl(baseline_path)
        lines.extend(_summarize_baseline(baseline))
    if surface_path.exists():
        surface = _read_jsonl(surface_path)
        lines.extend(_summarize_surface(surface))
    output = OUTPUT_DIR / "summary.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(output.relative_to(ROOT_DIR))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def _summarize_baseline(records: list[dict[str, Any]]) -> list[str]:
    status_counts: dict[str, int] = {}
    checks: dict[str, int] = {}
    for record in records:
        status_counts[record["status"]] = status_counts.get(record["status"], 0) + 1
        for check in record.get("final_failed_checks") or []:
            checks[check] = checks.get(check, 0) + 1
    return [
        "## Baseline",
        "",
        f"- Runs: {len(records)}",
        f"- Status: {_json(status_counts)}",
        f"- Failed checks: {_json(checks)}",
        "",
    ]


def _summarize_surface(records: list[dict[str, Any]]) -> list[str]:
    by_version: dict[str, dict[str, Any]] = {}
    for record in records:
        version = record["prompt_version"]
        bucket = by_version.setdefault(version, {"runs": 0, "passed": 0, "checks": {}})
        bucket["runs"] += 1
        if record.get("gate", {}).get("passed"):
            bucket["passed"] += 1
        for check in record.get("gate", {}).get("failed_checks") or []:
            bucket["checks"][check] = bucket["checks"].get(check, 0) + 1
    lines = ["## Surface Story Candidates", ""]
    for version, stats in sorted(by_version.items()):
        pass_rate = stats["passed"] / stats["runs"] if stats["runs"] else 0
        lines.extend(
            [
                f"### {version}",
                "",
                f"- Runs: {stats['runs']}",
                f"- Passed: {stats['passed']} ({pass_rate:.0%})",
                f"- Failed checks: {_json(stats['checks'])}",
                "",
            ]
        )
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline prompt testing lab.")
    subparsers = parser.add_subparsers(required=True)

    baseline_parser = subparsers.add_parser("baseline")
    _add_provider_args(baseline_parser)
    baseline_parser.add_argument("--topic", default="便利商店")
    baseline_parser.add_argument("--runs", type=int, default=3)
    baseline_parser.add_argument("--interpret-version", default="interpret_topic.v0")
    baseline_parser.add_argument("--core-version", default="generate_core_truth.v0")
    baseline_parser.add_argument("--expand-version", default="expand_truth.v0")
    baseline_parser.add_argument("--surface-version", default="write_surface_story.v0")
    baseline_parser.add_argument("--review-version", default="review_puzzle.v0")
    baseline_parser.set_defaults(func=run_baseline)

    surface_parser = subparsers.add_parser("surface")
    _add_provider_args(surface_parser)
    surface_parser.add_argument("--baseline-file", default=str(OUTPUT_DIR / "baseline-runs.jsonl"))
    surface_parser.add_argument("--versions", action="append")
    surface_parser.add_argument("--repeats", type=int, default=3)
    surface_parser.add_argument("--limit", type=int)
    surface_parser.set_defaults(func=run_surface)

    summarize_parser = subparsers.add_parser("summarize")
    summarize_parser.set_defaults(func=summarize)

    args = parser.parse_args()
    args.func(args)


def _add_provider_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--provider",
        choices=["ollama", "openai-compatible"],
        default="ollama",
    )
    parser.add_argument(
        "--openai-base-url",
        default="http://localhost:18080/v1",
        help="OpenAI-compatible base URL, for example http://192.168.192.1:18080/v1.",
    )
    parser.add_argument(
        "--openai-model",
        default="qwen3.6-35b-a3b",
        help="Model id returned by the OpenAI-compatible /v1/models endpoint.",
    )
    parser.add_argument(
        "--openai-max-tokens",
        type=int,
        default=0,
        help="max_tokens for OpenAI-compatible chat completions. Use 0 to omit it.",
    )
    parser.add_argument(
        "--request-timeout",
        type=int,
        help="Override llm.request_timeout_seconds for long local model calls.",
    )


def _apply_runtime_overrides(settings: Settings, args: argparse.Namespace) -> None:
    if args.request_timeout:
        settings.llm.request_timeout_seconds = args.request_timeout


if __name__ == "__main__":
    main()
