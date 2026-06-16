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


OUTPUT_DIR = ROOT_DIR / "docs" / "prompt-tests" / "pipeline-v2"
RAW_DIR = OUTPUT_DIR / "raw"


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


def _invoke_structured(
    settings: Settings,
    task: str,
    schema: type[Any],
    messages: list[SystemMessage | HumanMessage],
    temperature: float,
) -> dict[str, Any]:
    start = perf_counter()
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
    return {
        variant.version: variant
        for variant in (v0, v1, v2, v3, v4, v5, v6, v7)
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
    return {variant.version: variant for variant in (v0, v1, v2, v3)}


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
    settings = get_settings()
    surface_variant = _surface_prompt_variants(settings)[args.surface_version]
    core_variant = _core_truth_prompt_variants(settings)[args.core_version]
    for index in range(args.runs):
        record = _run_pipeline_once(settings, args.topic, index, core_variant, surface_variant)
        raw_path = (
            RAW_DIR
            / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_pipeline_{core_variant.version}_{surface_variant.version}_{_slug(args.topic)}_{index + 1}.json"
        )
        _write_json(raw_path, record)
        _append_jsonl(OUTPUT_DIR / "baseline-runs.jsonl", record | {"raw_file": str(raw_path.relative_to(ROOT_DIR))})
        print(
            f"{record['status']} {surface_variant.version} {index + 1}/{args.runs} "
            f"core={core_variant.version} "
            f"target={record.get('final_target_node')} checks={record.get('final_failed_checks')} "
            f"{record['duration_ms']}ms {raw_path.relative_to(ROOT_DIR)}"
        )


def _run_pipeline_once(
    settings: Settings,
    topic: str,
    run_index: int,
    core_variant: PromptVariant,
    surface_variant: PromptVariant,
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
                SystemMessage(content=interpret_topic_system_prompt(settings.puzzle)),
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
                SystemMessage(content=expand_truth_system_prompt(settings.puzzle, settings.puzzle_generation)),
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
                        SystemMessage(content=review_puzzle_system_prompt(settings.puzzle)),
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
        "model": settings.ollama_model,
        "base_url": settings.ollama_base_url,
        "core_prompt_version": core_variant.version,
        "surface_prompt_version": surface_variant.version,
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
    settings = get_settings()
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
        "model": settings.ollama_model,
        "base_url": settings.ollama_base_url,
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
    baseline_parser.add_argument("--topic", default="便利商店")
    baseline_parser.add_argument("--runs", type=int, default=3)
    baseline_parser.add_argument("--core-version", default="generate_core_truth.v0")
    baseline_parser.add_argument("--surface-version", default="write_surface_story.v0")
    baseline_parser.set_defaults(func=run_baseline)

    surface_parser = subparsers.add_parser("surface")
    surface_parser.add_argument("--baseline-file", default=str(OUTPUT_DIR / "baseline-runs.jsonl"))
    surface_parser.add_argument("--versions", action="append")
    surface_parser.add_argument("--repeats", type=int, default=3)
    surface_parser.add_argument("--limit", type=int)
    surface_parser.set_defaults(func=run_surface)

    summarize_parser = subparsers.add_parser("summarize")
    summarize_parser.set_defaults(func=summarize)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
