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
from pydantic import BaseModel

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import Settings, get_settings
from app.llm.prompts import (
    expand_truth_system_prompt,
    expand_truth_user_prompt,
    extract_solution_facts_system_prompt,
    extract_solution_facts_user_prompt,
    generate_assumptions_system_prompt,
    generate_assumptions_user_prompt,
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
    AssumptionsDraft,
    CoreTruthDraft,
    PuzzleReviewResult,
    SolutionFactsDraft,
    SurfaceStoryDraft,
    TopicInterpretation,
    TruthDraft,
)


OUTPUT_DIR = ROOT_DIR / "docs" / "prompt-tests" / "pipeline-v2" / "round4"
RAW_DIR = OUTPUT_DIR / "raw"

ABSOLUTE_TERMS = (
    "全程無人",
    "完全沒有人",
    "沒有人靠近",
    "沒有人碰過",
    "沒人靠近",
    "無人靠近",
    "無人接近",
    "憑空消失",
    "凭空消失",
    "凭空",
    "不翼而飛",
)
VIEWPOINT_QUALIFIERS = (
    "看起來",
    "像是",
    "似乎",
    "以為",
    "誤以為",
    "監視器畫面",
    "監視畫面",
    "店員回頭時發現",
    "眾人",
)
PERSON_ACTION_TERMS = ("顧客", "客人", "店員", "男子", "女子", "拿走", "偷", "藏", "放", "靠近")
SOLUTION_LEAK_TERMS = (
    "顧客趁",
    "客人趁",
    "藏入外套",
    "藏進外套",
    "藏入大衣",
    "藏進大衣",
    "背包壓",
    "壓住自動門感應區",
    "拿走限定商品",
    "拿走商品",
    "利用自動門",
    "利用監視器死角",
)
LOW_PLAYABILITY_CORE_TERMS = (
    "貼錯",
    "標籤",
    "標示",
    "誤讀",
    "看錯",
    "試吃區",
    "促銷",
    "補貨",
    "打掃",
    "清潔",
    "盤點",
    "陳列",
    "單純誤會",
    "只是誤會",
)


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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _load_json_object(content: str) -> dict[str, Any]:
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
        raise ValueError("LLM output must be a JSON object.")
    return value


def _invoke_structured(
    settings: Settings,
    task: str,
    schema: type[BaseModel],
    messages: list[SystemMessage | HumanMessage],
    temperature: float,
) -> dict[str, Any]:
    start = perf_counter()
    payload: dict[str, Any] = {
        "model": settings.openai_compatible_model,
        "messages": [
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
        ],
        "temperature": temperature,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    if settings.llm.openai_compatible_max_tokens > 0:
        payload["max_tokens"] = settings.llm.openai_compatible_max_tokens
    request = Request(
        settings.openai_compatible_base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=settings.llm.request_timeout_seconds) as response:
        raw_response = json.loads(response.read().decode("utf-8"))
    content = raw_response["choices"][0]["message"].get("content") or ""
    parsed = schema.model_validate(_load_json_object(content))
    return {
        "task": task,
        "duration_ms": round((perf_counter() - start) * 1000, 2),
        "system_prompt": messages[0].content,
        "human_prompt": messages[1].content,
        "parsed": parsed,
        "raw": raw_response,
    }


def _surface_v10(settings: Settings) -> PromptVariant:
    base = write_surface_story_system_prompt(settings.puzzle, settings.puzzle_generation)
    return PromptVariant(
        "write_surface_story.v10-objective-guard",
        "\n".join(
            [
                base,
                "",
                "第四輪客觀性規則：",
                "- 謎面不得把角色主觀視角、監視器死角、事後誤判寫成絕對客觀事實。",
                "- 如果 truth 中實際有人或物造成事件，不可寫「全程無人」「完全沒有人」「沒有人靠近」「沒有人碰過」。",
                "- 「憑空消失」「不翼而飛」只能作為角色感受或視角限制，例如「店員回頭時發現...不見」「監視畫面看起來...」。",
                "- 允許使用視角限定詞：看起來、他以為、監視畫面像是、店員回頭時發現、眾人誤以為。",
                "- 每個強烈陳述都必須能被 truth 當成客觀事實支持；不能只為了製造謎面張力而誇大。",
            ]
        ),
    )


def _review_v2(settings: Settings) -> PromptVariant:
    base = review_puzzle_system_prompt(settings.puzzle)
    return PromptVariant(
        "review_puzzle.v2-objective-claim-check",
        "\n".join(
            [
                base,
                "",
                "第四輪強客觀陳述審核：",
                "- 逐一檢查 surface_story 中的強烈客觀詞：全程無人、完全沒有人、沒有人靠近、沒有人碰過、憑空消失、不翼而飛、自己、突然。",
                "- 若 truth 顯示事件其實由人物、物品或視角死角造成，surface_story 不可把它寫成絕對無人、無物、無接觸或憑空發生。",
                "- 若該陳述只是角色誤判或監視器視角限制，surface_story 必須有「看起來」「以為」「監視畫面像是」「店員回頭時發現」等限定。",
                "- 發現未被 truth 支持的強客觀陳述時，passed=false、target_node=write_surface_story。",
                "- revision_instruction 必須明確要求改成視角限定，不可要求改 truth。",
            ]
        ),
    )


def _facts_v2(settings: Settings) -> PromptVariant:
    base = extract_solution_facts_system_prompt(settings.puzzle)
    return PromptVariant(
        "extract_solution_facts.v2-minimum-required",
        "\n".join(
            [
                base,
                "",
                "第四輪最小通關門檻規則：",
                "- required_solution_facts 優先 2 到 3 條，只有無法涵蓋主要因果時才用 4 條。",
                "- required_solution_facts 只放玩家提交解答必須說出的最低必要事實。",
                "- 表面誤導校正通常放 supporting_facts；只有缺少它會讓答案變成另一個故事時，才放 required_solution_facts。",
                "- 不要把謎面描述、可由原因自然推出的結果、或玩家可忽略的執行細節放入 required_solution_facts。",
            ]
        ),
    )


def _core_v8(settings: Settings) -> PromptVariant:
    base = generate_core_truth_system_prompt(settings.puzzle)
    return PromptVariant(
        "generate_core_truth.v8-active-cause",
        "\n".join(
            [
                base,
                "",
                "第四輪核心可玩性規則：",
                "- 不得把核心原因寫成標籤貼錯、看錯標示、誤讀文字、以為是試吃區、促銷誤會、商品位置錯誤或單純誤會。",
                "- 真正原因必須是某人有目的的具體行動或具體隱藏條件，不是資訊標示本身錯誤。",
                "- abnormal_result 必須讓玩家追問「這個人為什麼要這樣做？」而不是只追問「他是不是看錯了？」",
                "- 解法要至少需要確認兩個面向：行動者做了什麼，以及該行動為何會造成表面異常。",
                "- 允許輕度日常違規或小型欺瞞，但不可變成複雜犯罪、秘密組織、暗號任務、專業制度或暴力事件。",
                "- 優先使用：留下收據證明時間地點、買了不拿以製造可見訊號、店員拒賣以阻止明確風險、顧客反覆做同一行動以引起特定人注意。",
            ]
        ),
    )


def _objective_claim_gate(surface_story: str, truth: str) -> dict[str, Any]:
    absolute_terms = [term for term in ABSOLUTE_TERMS if term in surface_story]
    has_viewpoint_qualifier = any(term in surface_story for term in VIEWPOINT_QUALIFIERS)
    truth_contains_person_action = any(term in truth for term in PERSON_ACTION_TERMS)
    unsupported = bool(absolute_terms and truth_contains_person_action and not has_viewpoint_qualifier)
    solution_leak_terms = [term for term in SOLUTION_LEAK_TERMS if term in surface_story]
    failed_checks = []
    if unsupported:
        failed_checks.append("surface_story_unsupported_absolute_terms")
    if solution_leak_terms:
        failed_checks.append("surface_story_leaks_solution")
    return {
        "surface_story_absolute_terms": absolute_terms,
        "surface_story_has_viewpoint_qualifier": has_viewpoint_qualifier,
        "surface_story_absolute_claim_supported_by_truth": not unsupported,
        "surface_story_solution_leak_terms": solution_leak_terms,
        "failed_checks": failed_checks,
        "passed": not failed_checks,
    }


def _sentence_count(text: str) -> int:
    return len([part for part in re.split(r"[。！？!?]+", text) if part.strip()])


def _surface_format_gate(surface_story: str, settings: Settings) -> dict[str, Any]:
    failed: list[str] = []
    if len(surface_story) < 50:
        failed.append("surface_story_too_short")
    if len(surface_story) > settings.puzzle_generation.strict_surface_story_max_chars:
        failed.append("surface_story_too_long")
    if _sentence_count(surface_story) != 2:
        failed.append("surface_story_sentence_count")
    if re.search(r"(其實|原來|因為|真相|目的|為了|實則|判斷|需要|驗證|背後)", surface_story):
        failed.append("surface_story_leaks_reason")
    return {
        "passed": not failed,
        "failed_checks": failed,
        "char_count": len(surface_story),
        "sentence_count": _sentence_count(surface_story),
    }


def _combined_surface_gate(surface_story: str, truth: str, settings: Settings) -> dict[str, Any]:
    format_gate = _surface_format_gate(surface_story, settings)
    objective_gate = _objective_claim_gate(surface_story, truth)
    failed = [*format_gate["failed_checks"], *objective_gate["failed_checks"]]
    return {
        "passed": not failed,
        "failed_checks": failed,
        "format": format_gate,
        "objective_claim": objective_gate,
    }


def _core_gate(core: CoreTruthDraft) -> dict[str, Any]:
    text = "\n".join(
        [
            core.core_truth,
            core.cause,
            core.actor_action,
            core.abnormal_result,
            core.misdirection,
        ]
    )
    low_terms = [term for term in LOW_PLAYABILITY_CORE_TERMS if term in text]
    has_actor_action = bool(core.actor_action.strip()) and bool(core.abnormal_result.strip())
    failed_checks = []
    if low_terms:
        failed_checks.append("core_truth_low_playability_terms")
    if not has_actor_action:
        failed_checks.append("core_truth_missing_actor_action")
    return {
        "passed": not failed_checks,
        "failed_checks": failed_checks,
        "low_playability_terms": low_terms,
    }


def _convenience_case() -> dict[str, Any]:
    interpretation = TopicInterpretation(
        title="便利商店",
        scene="便利商店",
        objects=[],
        actors=[],
        explicit_results=[],
        hard_constraints=["故事主要場景必須是便利商店"],
        open_space="可補一個日常人物行為異常，但不得把主線寫成店務流程或商品狀態。",
    )
    core_truth = CoreTruthDraft(
        core_truth="顧客把背包壓在自動門感應區，使門反覆開合並遮住監視器視角，趁機拿走限定商品。",
        cause="顧客想利用自動門感應區與監視器死角掩護自己。",
        actor_action="顧客將背包壓住自動門感應區後走向貨架拿走商品。",
        abnormal_result="自動門反覆開合，限定商品在監視畫面看似無人靠近時消失。",
        misdirection="眾人容易以為是幽靈或內部人員造成。",
    )
    truth = TruthDraft(
        truth=(
            "限定商品不是自己消失，也不是幽靈作祟。顧客進店時故意把很重的背包放在自動門感應區附近，"
            "讓門持續開合並製造監視器畫面的遮擋。他趁店員注意門口時走到後方貨架，把限定商品藏進外套內層。"
            "監視器主要拍到反覆晃動的門與空出的貨架，沒有清楚拍到他靠近商品的角度，所以店員和旁人誤以為全程沒人靠近。"
        )
    )
    facts = SolutionFactsDraft(
        required_solution_facts=[
            {"id": "actor", "role": "actor", "fact": "顧客是造成商品消失的人"},
            {"id": "action", "role": "action", "fact": "顧客用背包壓住自動門感應區並趁機拿走商品"},
            {"id": "cause", "role": "cause", "fact": "自動門與監視器死角掩護了他的行動"},
        ],
        supporting_facts=[
            {"id": "misdirection", "fact": "旁人把監視畫面誤解成全程沒人靠近或幽靈作祟"},
            {"id": "hide", "fact": "商品被藏進外套內層帶離現場"},
        ],
    )
    assumptions = AssumptionsDraft(
        misleading_assumptions=["幽靈作祟", "店員內部作案"],
        forbidden_assumptions=["商品自己移動", "沒有任何顧客接近貨架"],
    )
    return {
        "topic": "便利商店",
        "interpretation": interpretation,
        "core_truth": core_truth,
        "truth": truth,
        "solution_facts": facts,
        "assumptions": assumptions,
        "bad_surface_story": "便利商店的自動門反覆開合，限定商品卻不翼而飛，全程無人靠近。監視器拍下空門晃動的畫面後，店內眾人皆以為是幽靈作祟。",
    }


def run_surface(args: argparse.Namespace) -> None:
    settings = _settings_from_args(args)
    case = _convenience_case()
    variant = _surface_v10(settings)
    for index in range(args.runs):
        start = perf_counter()
        status = "ok"
        error = None
        call: dict[str, Any] | None = None
        try:
            call = _invoke_structured(
                settings,
                "write_surface_story",
                SurfaceStoryDraft,
                [
                    SystemMessage(content=variant.system_prompt),
                    HumanMessage(
                        content=write_surface_story_user_prompt(
                            case["topic"],
                            case["interpretation"],
                            case["truth"],
                            case["solution_facts"],
                        )
                    ),
                ],
                settings.llm.generation_temperature,
            )
            surface = call["parsed"].surface_story
            gate = _combined_surface_gate(surface, case["truth"].truth, settings)
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error = f"{type(exc).__name__}: {exc}"
            surface = ""
            gate = {"passed": False, "failed_checks": ["error"]}
        record = {
            "created_at": _now(),
            "task": "round4_surface_objective",
            "status": status,
            "error": error,
            "provider": "openai-compatible",
            "model": settings.openai_compatible_model,
            "base_url": settings.openai_compatible_base_url,
            "prompt_version": variant.version,
            "case": "convenience_store_objective_claim",
            "run_index": index,
            "duration_ms": round((perf_counter() - start) * 1000, 2),
            "surface_story": surface,
            "truth": case["truth"].truth,
            "gate": gate,
            "call": _dump(call) if call else None,
        }
        _save_record("surface-runs.jsonl", record)
        print(f"{status} surface {index + 1}/{args.runs} pass={gate['passed']} checks={gate['failed_checks']}")


def run_review(args: argparse.Namespace) -> None:
    settings = _settings_from_args(args)
    case = _convenience_case()
    variant = _review_v2(settings)
    surface_cases = [
        ("bad_absolute", case["bad_surface_story"], False),
        (
            "qualified_viewpoint",
            "便利商店的自動門反覆開合，限定商品也在店員沒注意時消失了。監視器畫面看起來只有空門晃動，店內眾人因此以為是幽靈作祟。",
            True,
        ),
    ]
    for case_name, surface_text, expected_pass in surface_cases:
        start = perf_counter()
        status = "ok"
        error = None
        call: dict[str, Any] | None = None
        try:
            surface = SurfaceStoryDraft(surface_story=surface_text)
            call = _invoke_structured(
                settings,
                "review_puzzle",
                PuzzleReviewResult,
                [
                    SystemMessage(content=variant.system_prompt),
                    HumanMessage(
                        content=review_puzzle_user_prompt(
                            case["topic"],
                            case["interpretation"],
                            case["core_truth"],
                            case["truth"],
                            case["solution_facts"],
                            surface,
                            case["assumptions"],
                        )
                    ),
                ],
                settings.llm.judge_temperature,
            )
            review = call["parsed"]
            reviewer_detected = not review.passed and review.target_node == "write_surface_story"
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error = f"{type(exc).__name__}: {exc}"
            review = None
            reviewer_detected = False
        record = {
            "created_at": _now(),
            "task": "round4_review_objective",
            "status": status,
            "error": error,
            "provider": "openai-compatible",
            "model": settings.openai_compatible_model,
            "base_url": settings.openai_compatible_base_url,
            "prompt_version": variant.version,
            "case": case_name,
            "expected_pass": expected_pass,
            "duration_ms": round((perf_counter() - start) * 1000, 2),
            "surface_story": surface_text,
            "reviewer_detected_unsupported_absolute_claim": reviewer_detected,
            "review": _dump(review),
            "call": _dump(call) if call else None,
        }
        _save_record("review-runs.jsonl", record)
        print(f"{status} review {case_name} detected={reviewer_detected} expected_pass={expected_pass}")


def run_facts(args: argparse.Namespace) -> None:
    settings = _settings_from_args(args)
    case = _convenience_case()
    variant = _facts_v2(settings)
    for index in range(args.runs):
        start = perf_counter()
        status = "ok"
        error = None
        call: dict[str, Any] | None = None
        try:
            call = _invoke_structured(
                settings,
                "extract_solution_facts",
                SolutionFactsDraft,
                [
                    SystemMessage(content=variant.system_prompt),
                    HumanMessage(content=extract_solution_facts_user_prompt(case["core_truth"], case["truth"])),
                ],
                settings.llm.generation_temperature,
            )
            facts = call["parsed"]
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error = f"{type(exc).__name__}: {exc}"
            facts = SolutionFactsDraft()
        required_count = len(facts.required_solution_facts)
        record = {
            "created_at": _now(),
            "task": "round4_extract_solution_facts",
            "status": status,
            "error": error,
            "provider": "openai-compatible",
            "model": settings.openai_compatible_model,
            "base_url": settings.openai_compatible_base_url,
            "prompt_version": variant.version,
            "case": "convenience_store_objective_claim",
            "run_index": index,
            "duration_ms": round((perf_counter() - start) * 1000, 2),
            "required_fact_count": required_count,
            "required_fact_count_passed": 2 <= required_count <= 3,
            "facts": _dump(facts),
            "call": _dump(call) if call else None,
        }
        _save_record("facts-runs.jsonl", record)
        print(f"{status} facts {index + 1}/{args.runs} required={required_count}")


def run_core(args: argparse.Namespace) -> None:
    settings = _settings_from_args(args)
    variant = _core_v8(settings)
    interpretation = TopicInterpretation(
        title=args.topic,
        scene=args.topic,
        objects=[],
        actors=[],
        explicit_results=[],
        hard_constraints=[f"故事主要場景必須是{args.topic}"],
        open_space="可補一個日常人物行為異常，但不得把主線寫成店務流程、商品狀態或單純誤會。",
    )
    for index in range(args.runs):
        start = perf_counter()
        status = "ok"
        error = None
        call: dict[str, Any] | None = None
        try:
            call = _invoke_structured(
                settings,
                "generate_core_truth",
                CoreTruthDraft,
                [
                    SystemMessage(content=variant.system_prompt),
                    HumanMessage(content=generate_core_truth_user_prompt(args.topic, interpretation)),
                ],
                settings.llm.generation_temperature,
            )
            core = call["parsed"]
            gate = _core_gate(core)
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error = f"{type(exc).__name__}: {exc}"
            core = None
            gate = {"passed": False, "failed_checks": ["error"]}
        record = {
            "created_at": _now(),
            "task": "round4_core_truth_candidate",
            "status": status,
            "error": error,
            "provider": "openai-compatible",
            "model": settings.openai_compatible_model,
            "base_url": settings.openai_compatible_base_url,
            "prompt_version": variant.version,
            "topic": args.topic,
            "run_index": index,
            "duration_ms": round((perf_counter() - start) * 1000, 2),
            "gate": gate,
            "core_truth": _dump(core),
            "call": _dump(call) if call else None,
        }
        _save_record("core-runs.jsonl", record)
        print(f"{status} core {index + 1}/{args.runs} pass={gate['passed']} checks={gate['failed_checks']}")


def run_pipeline(args: argparse.Namespace) -> None:
    settings = _settings_from_args(args)
    variants = {
        "core": _core_v8(settings),
        "surface": _surface_v10(settings),
        "facts": _facts_v2(settings),
        "review": _review_v2(settings),
    }
    topics = args.topic or ["便利商店"]
    for topic in topics:
        for index in range(args.runs):
            record = _run_pipeline_once(settings, topic, index, variants)
            _save_record("pipeline-runs.jsonl", record)
            print(
                f"{record['status']} pipeline {topic} {index + 1}/{args.runs} "
                f"review={record.get('review_passed')} checks={record.get('surface_gate', {}).get('failed_checks')} "
                f"{record['duration_ms']}ms"
            )


def _run_pipeline_once(
    settings: Settings,
    topic: str,
    run_index: int,
    variants: dict[str, PromptVariant],
) -> dict[str, Any]:
    start = perf_counter()
    nodes: list[dict[str, Any]] = []
    status = "ok"
    error = None
    surface_gate: dict[str, Any] = {}
    review_passed: bool | None = None
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
                SystemMessage(content=variants["core"].system_prompt),
                HumanMessage(content=generate_core_truth_user_prompt(topic, interpretation)),
            ],
            settings.llm.generation_temperature,
        )
        core = core_call["parsed"]
        nodes.append(_node_record(core_call))

        truth_call = _invoke_structured(
            settings,
            "expand_truth",
            TruthDraft,
            [
                SystemMessage(content=expand_truth_system_prompt(settings.puzzle, settings.puzzle_generation)),
                HumanMessage(content=expand_truth_user_prompt(topic, interpretation, core)),
            ],
            settings.llm.generation_temperature,
        )
        truth = truth_call["parsed"]
        nodes.append(_node_record(truth_call))

        facts_call = _invoke_structured(
            settings,
            "extract_solution_facts",
            SolutionFactsDraft,
            [
                SystemMessage(content=variants["facts"].system_prompt),
                HumanMessage(content=extract_solution_facts_user_prompt(core, truth)),
            ],
            settings.llm.generation_temperature,
        )
        facts = facts_call["parsed"]
        nodes.append(_node_record(facts_call))

        surface_call = _invoke_structured(
            settings,
            "write_surface_story",
            SurfaceStoryDraft,
            [
                SystemMessage(content=variants["surface"].system_prompt),
                HumanMessage(content=write_surface_story_user_prompt(topic, interpretation, truth, facts)),
            ],
            settings.llm.generation_temperature,
        )
        surface = surface_call["parsed"]
        nodes.append(_node_record(surface_call))
        surface_gate = _combined_surface_gate(surface.surface_story, truth.truth, settings)

        assumptions_call = _invoke_structured(
            settings,
            "generate_assumptions",
            AssumptionsDraft,
            [
                SystemMessage(content=generate_assumptions_system_prompt(settings.puzzle)),
                HumanMessage(content=generate_assumptions_user_prompt(truth, facts, surface)),
            ],
            settings.llm.generation_temperature,
        )
        assumptions = assumptions_call["parsed"]
        nodes.append(_node_record(assumptions_call))

        review_call = _invoke_structured(
            settings,
            "review_puzzle",
            PuzzleReviewResult,
            [
                SystemMessage(content=variants["review"].system_prompt),
                HumanMessage(
                    content=review_puzzle_user_prompt(
                        topic,
                        interpretation,
                        core,
                        truth,
                        facts,
                        surface,
                        assumptions,
                    )
                ),
            ],
            settings.llm.judge_temperature,
        )
        review = review_call["parsed"]
        review_passed = review.passed
        nodes.append(_node_record(review_call))
    except Exception as exc:  # noqa: BLE001
        status = "error"
        error = f"{type(exc).__name__}: {exc}"
    return {
        "created_at": _now(),
        "task": "round4_pipeline_candidate",
        "status": status,
        "error": error,
        "provider": "openai-compatible",
        "model": settings.openai_compatible_model,
        "base_url": settings.openai_compatible_base_url,
        "topic": topic,
        "run_index": run_index,
        "duration_ms": round((perf_counter() - start) * 1000, 2),
        "prompt_versions": {key: value.version for key, value in variants.items()},
        "surface_gate": surface_gate,
        "review_passed": review_passed,
        "nodes": nodes,
    }


def _node_record(call: dict[str, Any]) -> dict[str, Any]:
    return {
        "task": call["task"],
        "duration_ms": call["duration_ms"],
        "system_prompt": call["system_prompt"],
        "human_prompt": call["human_prompt"],
        "parsed": _dump(call["parsed"]),
        "raw": call["raw"],
    }


def summarize(args: argparse.Namespace) -> None:
    settings = _settings_from_args(args)
    del settings
    records_by_name = {
        "core": _read_jsonl(OUTPUT_DIR / "core-runs.jsonl"),
        "surface": _read_jsonl(OUTPUT_DIR / "surface-runs.jsonl"),
        "review": _read_jsonl(OUTPUT_DIR / "review-runs.jsonl"),
        "facts": _read_jsonl(OUTPUT_DIR / "facts-runs.jsonl"),
        "pipeline": _read_jsonl(OUTPUT_DIR / "pipeline-runs.jsonl"),
    }
    lines = [
        "# Round 4 Prompt 測試紀錄",
        "",
        f"更新時間：{_now()}",
        "",
        "## 範圍",
        "",
        "- 測試 `write_surface_story.v10-objective-guard` 是否避免未被 truth 支持的絕對客觀謎面。",
        "- 測試 `review_puzzle.v2-objective-claim-check` 是否能打回強客觀詞錯誤。",
        "- 測試 `extract_solution_facts.v2-minimum-required` 是否把 required facts 收斂到最低通關門檻。",
        "",
    ]
    core = records_by_name["core"]
    if core:
        passed = sum(1 for item in core if item.get("gate", {}).get("passed"))
        checks = _count_checks(item.get("gate", {}).get("failed_checks") for item in core)
        lines.extend(
            [
                "## Core Truth Active Cause",
                "",
                f"- Runs: {len(core)}",
                f"- Passed: {passed}",
                f"- Failed checks: {json.dumps(checks, ensure_ascii=False)}",
                "",
            ]
        )
    surface = records_by_name["surface"]
    if surface:
        passed = sum(1 for item in surface if item.get("gate", {}).get("passed"))
        checks = _count_checks(item.get("gate", {}).get("failed_checks") for item in surface)
        lines.extend(
            [
                "## Surface Objective Gate",
                "",
                f"- Runs: {len(surface)}",
                f"- Passed: {passed}",
                f"- Failed checks: {json.dumps(checks, ensure_ascii=False)}",
                "",
            ]
        )
    review = records_by_name["review"]
    if review:
        bad = [item for item in review if item["case"] == "bad_absolute"]
        detected = sum(1 for item in bad if item.get("reviewer_detected_unsupported_absolute_claim"))
        false_kill = sum(
            1
            for item in review
            if item.get("expected_pass") and item.get("review", {}).get("passed") is False
        )
        lines.extend(
            [
                "## Reviewer Objective Claim Detection",
                "",
                f"- Bad absolute cases: {len(bad)}",
                f"- Detected: {detected}",
                f"- Qualified false kills: {false_kill}",
                "",
            ]
        )
    facts = records_by_name["facts"]
    if facts:
        passed = sum(1 for item in facts if item.get("required_fact_count_passed"))
        counts = [item.get("required_fact_count") for item in facts]
        lines.extend(
            [
                "## Solution Facts Minimum Required",
                "",
                f"- Runs: {len(facts)}",
                f"- Required fact counts: {json.dumps(counts, ensure_ascii=False)}",
                f"- Count pass: {passed}",
                "",
            ]
        )
    pipeline = records_by_name["pipeline"]
    if pipeline:
        ok = sum(1 for item in pipeline if item.get("status") == "ok")
        surface_passed = sum(1 for item in pipeline if item.get("surface_gate", {}).get("passed"))
        review_passed = sum(1 for item in pipeline if item.get("review_passed"))
        lines.extend(
            [
                "## Full Pipeline Smoke",
                "",
                f"- Runs: {len(pipeline)}",
                f"- Status ok: {ok}",
                f"- Surface gate passed: {surface_passed}",
                f"- Reviewer passed: {review_passed}",
                "",
            ]
        )
    output = OUTPUT_DIR / "summary.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(output.relative_to(ROOT_DIR))


def _count_checks(check_lists: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for checks in check_lists:
        for check in checks or []:
            counts[check] = counts.get(check, 0) + 1
    return counts


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def _save_record(name: str, record: dict[str, Any]) -> None:
    raw_path = RAW_DIR / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{record['task']}_{_slug(record.get('case') or record.get('topic') or 'case')}.json"
    _write_json(raw_path, record)
    _append_jsonl(OUTPUT_DIR / name, record | {"raw_file": str(raw_path.relative_to(ROOT_DIR))})


def _settings_from_args(args: argparse.Namespace) -> Settings:
    settings = get_settings()
    if args.base_url:
        settings.openai_compatible_base_url = args.base_url
    if args.model:
        settings.openai_compatible_model = args.model
    if args.timeout:
        settings.llm.request_timeout_seconds = args.timeout
    return settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Round 4 prompt objective-claim lab.")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout", type=int, default=900)
    subparsers = parser.add_subparsers(required=True)

    surface = subparsers.add_parser("surface")
    surface.add_argument("--runs", type=int, default=3)
    surface.set_defaults(func=run_surface)

    review = subparsers.add_parser("review")
    review.set_defaults(func=run_review)

    facts = subparsers.add_parser("facts")
    facts.add_argument("--runs", type=int, default=3)
    facts.set_defaults(func=run_facts)

    core = subparsers.add_parser("core")
    core.add_argument("--topic", default="便利商店")
    core.add_argument("--runs", type=int, default=3)
    core.set_defaults(func=run_core)

    pipeline = subparsers.add_parser("pipeline")
    pipeline.add_argument("--topic", action="append")
    pipeline.add_argument("--runs", type=int, default=1)
    pipeline.set_defaults(func=run_pipeline)

    summary = subparsers.add_parser("summarize")
    summary.set_defaults(func=summarize)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
