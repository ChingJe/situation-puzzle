from __future__ import annotations

from collections.abc import Sequence
import logging
from time import perf_counter
from typing import Any, Protocol, TypeVar
from urllib.parse import urlparse
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.errors import ApiErrorCode, AppError
from app.llm.prompts import (
    answer_question_system_prompt,
    answer_question_user_prompt,
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
    judge_solution_system_prompt,
    judge_solution_user_prompt,
    puzzle_generation_system_prompt,
    puzzle_generation_user_prompt,
    review_puzzle_system_prompt,
    review_puzzle_user_prompt,
    write_surface_story_system_prompt,
    write_surface_story_user_prompt,
)
from app.models import (
    CoreTruthDraft,
    ForbiddenAssumptionsDraft,
    KeyFactsDraft,
    Puzzle,
    PuzzleDraft,
    PuzzleReviewResult,
    QuestionJudgement,
    QuestionRecord,
    SolutionJudgement,
    SurfaceStoryDraft,
    TopicInterpretation,
    TruthDraft,
)
from app.observability import bind_log_context, log_event, log_raw_message


T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger("app.llm.client")


class LlmClient(Protocol):
    def interpret_topic(self, topic: str) -> TopicInterpretation: ...

    def generate_core_truth(
        self,
        topic: str,
        interpretation: TopicInterpretation,
        review_instruction: str | None = None,
    ) -> CoreTruthDraft: ...

    def expand_truth(
        self,
        topic: str,
        interpretation: TopicInterpretation,
        core_truth: CoreTruthDraft,
        review_instruction: str | None = None,
    ) -> TruthDraft: ...

    def extract_key_facts(self, truth: TruthDraft) -> KeyFactsDraft: ...

    def write_surface_story(
        self,
        topic: str,
        interpretation: TopicInterpretation,
        truth: TruthDraft,
        key_facts: KeyFactsDraft,
        review_instruction: str | None = None,
    ) -> SurfaceStoryDraft: ...

    def generate_forbidden_assumptions(
        self,
        truth: TruthDraft,
        key_facts: KeyFactsDraft,
        surface_story: SurfaceStoryDraft,
    ) -> ForbiddenAssumptionsDraft: ...

    def review_puzzle(
        self,
        topic: str,
        interpretation: TopicInterpretation,
        core_truth: CoreTruthDraft,
        truth: TruthDraft,
        key_facts: KeyFactsDraft,
        surface_story: SurfaceStoryDraft,
        forbidden_assumptions: list[str],
    ) -> PuzzleReviewResult: ...

    def answer_question(
        self,
        puzzle: Puzzle,
        question: str,
        history: list[QuestionRecord],
    ) -> QuestionJudgement: ...

    def judge_solution(
        self,
        puzzle: Puzzle,
        solution: str,
        history: list[QuestionRecord],
    ) -> SolutionJudgement: ...

    def health_check(self) -> dict[str, object]: ...


class OllamaLlmClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _chat(self, temperature: float) -> ChatOllama:
        return ChatOllama(
            model=self.settings.ollama_model,
            base_url=self.settings.ollama_base_url,
            temperature=temperature,
            client_kwargs={"timeout": self.settings.llm.request_timeout_seconds},
        )

    def _invoke_structured(
        self,
        task: str,
        schema: type[T],
        messages: list[SystemMessage | HumanMessage],
        temperature: float,
    ) -> T:
        start = perf_counter()
        llm_call_id = f"llm_{uuid4().hex}"
        last_error: Exception | None = None
        attempts = (
            self.settings.llm.request_max_retries
            + self.settings.llm.structured_output_max_retries
            + 1
        )
        with bind_log_context(llm_call_id=llm_call_id):
            log_event(
                logger,
                "llm.call.started",
                llm_call_id=llm_call_id,
                task=task,
                model=self.settings.ollama_model,
                base_url_host=_base_url_host(self.settings.ollama_base_url),
                temperature=temperature,
                request_timeout_seconds=self.settings.llm.request_timeout_seconds,
                output_schema=schema.__name__,
                prompt_summary=_prompt_summary(messages),
            )
            self._log_prompt_messages(task, messages, llm_call_id)
            for attempt_index in range(attempts):
                try:
                    model = self._chat(temperature).with_structured_output(
                        schema,
                        include_raw=True,
                    )
                    result = model.invoke(messages)
                    raw_response = result.get("raw") if isinstance(result, dict) else result
                    parsed = result.get("parsed") if isinstance(result, dict) else result
                    parsing_error = (
                        result.get("parsing_error") if isinstance(result, dict) else None
                    )
                    if self.settings.logging.raw_message_include_llm_responses:
                        log_raw_message(
                            self.settings,
                            "llm.raw_response",
                            task,
                            _raw_response_payload(raw_response),
                            content_type="json",
                            llm_call_id=llm_call_id,
                        )
                    if parsing_error is not None:
                        raise parsing_error
                    output = parsed if isinstance(parsed, schema) else schema.model_validate(parsed)
                    if self.settings.logging.raw_message_include_parsed_outputs:
                        log_raw_message(
                            self.settings,
                            "llm.parsed_output",
                            task,
                            output.model_dump(mode="json"),
                            content_type="json",
                            llm_call_id=llm_call_id,
                        )
                    log_event(
                        logger,
                        "llm.call.finished",
                        llm_call_id=llm_call_id,
                        task=task,
                        output_schema=schema.__name__,
                        retry_count=attempt_index,
                        duration_ms=round((perf_counter() - start) * 1000, 2),
                    )
                    return output
                except ValidationError as exc:
                    last_error = exc
                    log_event(
                        logger,
                        "llm.call.retry",
                        level=logging.WARNING,
                        llm_call_id=llm_call_id,
                        task=task,
                        retry_index=attempt_index + 1,
                        retry_reason="validation_error",
                        exception_type=type(exc).__name__,
                        message=_truncate(str(exc)),
                    )
                except Exception as exc:
                    last_error = exc
                    log_event(
                        logger,
                        "llm.call.retry",
                        level=logging.WARNING,
                        llm_call_id=llm_call_id,
                        task=task,
                        retry_index=attempt_index + 1,
                        retry_reason="request_error",
                        exception_type=type(exc).__name__,
                        message=_truncate(str(exc)),
                    )
                    message = str(exc).lower()
                    if any(token in message for token in ("connection", "timeout", "refused")):
                        continue
        code = ApiErrorCode.LLM_OUTPUT_INVALID
        if last_error and any(
            token in str(last_error).lower()
            for token in ("connection", "timeout", "refused", "unavailable")
        ):
            code = ApiErrorCode.LLM_UNAVAILABLE
        log_event(
            logger,
            "llm.call.failed",
            level=logging.ERROR,
            llm_call_id=llm_call_id,
            task=task,
            error_code=code.value,
            retry_count=attempts,
            duration_ms=round((perf_counter() - start) * 1000, 2),
            exception_type=type(last_error).__name__ if last_error else None,
        )
        raise AppError(code, status_code=503 if code == ApiErrorCode.LLM_UNAVAILABLE else 500)

    def generate_puzzle(self, topic: str) -> PuzzleDraft:
        return self._invoke_structured(
            "generate_puzzle",
            PuzzleDraft,
            [
                SystemMessage(content=puzzle_generation_system_prompt(self.settings.puzzle)),
                HumanMessage(content=puzzle_generation_user_prompt(topic)),
            ],
            self.settings.llm.generation_temperature,
        )

    def interpret_topic(self, topic: str) -> TopicInterpretation:
        return self._invoke_structured(
            "interpret_topic",
            TopicInterpretation,
            [
                SystemMessage(content=interpret_topic_system_prompt(self.settings.puzzle)),
                HumanMessage(content=interpret_topic_user_prompt(topic)),
            ],
            self.settings.llm.generation_temperature,
        )

    def generate_core_truth(
        self,
        topic: str,
        interpretation: TopicInterpretation,
        review_instruction: str | None = None,
    ) -> CoreTruthDraft:
        return self._invoke_structured(
            "generate_core_truth",
            CoreTruthDraft,
            [
                SystemMessage(content=generate_core_truth_system_prompt(self.settings.puzzle)),
                HumanMessage(
                    content=generate_core_truth_user_prompt(
                        topic,
                        interpretation,
                        review_instruction,
                    )
                ),
            ],
            self.settings.llm.generation_temperature,
        )

    def expand_truth(
        self,
        topic: str,
        interpretation: TopicInterpretation,
        core_truth: CoreTruthDraft,
        review_instruction: str | None = None,
    ) -> TruthDraft:
        return self._invoke_structured(
            "expand_truth",
            TruthDraft,
            [
                SystemMessage(
                    content=expand_truth_system_prompt(
                        self.settings.puzzle,
                        self.settings.puzzle_generation,
                    )
                ),
                HumanMessage(
                    content=expand_truth_user_prompt(
                        topic,
                        interpretation,
                        core_truth,
                        review_instruction,
                    )
                ),
            ],
            self.settings.llm.generation_temperature,
        )

    def extract_key_facts(self, truth: TruthDraft) -> KeyFactsDraft:
        return self._invoke_structured(
            "extract_key_facts",
            KeyFactsDraft,
            [
                SystemMessage(content=extract_key_facts_system_prompt(self.settings.puzzle)),
                HumanMessage(content=extract_key_facts_user_prompt(truth)),
            ],
            self.settings.llm.generation_temperature,
        )

    def write_surface_story(
        self,
        topic: str,
        interpretation: TopicInterpretation,
        truth: TruthDraft,
        key_facts: KeyFactsDraft,
        review_instruction: str | None = None,
    ) -> SurfaceStoryDraft:
        return self._invoke_structured(
            "write_surface_story",
            SurfaceStoryDraft,
            [
                SystemMessage(
                    content=write_surface_story_system_prompt(
                        self.settings.puzzle,
                        self.settings.puzzle_generation,
                    )
                ),
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
            self.settings.llm.generation_temperature,
        )

    def generate_forbidden_assumptions(
        self,
        truth: TruthDraft,
        key_facts: KeyFactsDraft,
        surface_story: SurfaceStoryDraft,
    ) -> ForbiddenAssumptionsDraft:
        return self._invoke_structured(
            "generate_forbidden_assumptions",
            ForbiddenAssumptionsDraft,
            [
                SystemMessage(content=forbidden_assumptions_system_prompt(self.settings.puzzle)),
                HumanMessage(
                    content=forbidden_assumptions_user_prompt(
                        truth,
                        key_facts,
                        surface_story,
                    )
                ),
            ],
            self.settings.llm.generation_temperature,
        )

    def review_puzzle(
        self,
        topic: str,
        interpretation: TopicInterpretation,
        core_truth: CoreTruthDraft,
        truth: TruthDraft,
        key_facts: KeyFactsDraft,
        surface_story: SurfaceStoryDraft,
        forbidden_assumptions: list[str],
    ) -> PuzzleReviewResult:
        return self._invoke_structured(
            "review_puzzle",
            PuzzleReviewResult,
            [
                SystemMessage(content=review_puzzle_system_prompt(self.settings.puzzle)),
                HumanMessage(
                    content=review_puzzle_user_prompt(
                        topic,
                        interpretation,
                        core_truth,
                        truth,
                        key_facts,
                        surface_story,
                        forbidden_assumptions,
                    )
                ),
            ],
            self.settings.llm.judge_temperature,
        )

    def answer_question(
        self,
        puzzle: Puzzle,
        question: str,
        history: list[QuestionRecord],
    ) -> QuestionJudgement:
        return self._invoke_structured(
            "answer_question",
            QuestionJudgement,
            [
                SystemMessage(content=answer_question_system_prompt()),
                HumanMessage(content=answer_question_user_prompt(puzzle, question, history)),
            ],
            self.settings.llm.answer_temperature,
        )

    def judge_solution(
        self,
        puzzle: Puzzle,
        solution: str,
        history: list[QuestionRecord],
    ) -> SolutionJudgement:
        return self._invoke_structured(
            "judge_solution",
            SolutionJudgement,
            [
                SystemMessage(content=judge_solution_system_prompt()),
                HumanMessage(content=judge_solution_user_prompt(puzzle, solution, history)),
            ],
            self.settings.llm.judge_temperature,
        )

    def _log_prompt_messages(
        self,
        task: str,
        messages: list[SystemMessage | HumanMessage],
        llm_call_id: str,
    ) -> None:
        if not self.settings.logging.raw_message_include_llm_prompts:
            return
        for message in messages:
            content = message.content if isinstance(message.content, str) else str(message.content)
            kind = "llm.system_prompt" if isinstance(message, SystemMessage) else "llm.human_prompt"
            log_raw_message(
                self.settings,
                kind,
                task,
                content,
                content_type="text",
                llm_call_id=llm_call_id,
            )

    def health_check(self) -> dict[str, object]:
        start = perf_counter()
        tags_url = self.settings.ollama_base_url.rstrip("/") + "/api/tags"
        try:
            request = Request(tags_url, headers={"Accept": "application/json"})
            with urlopen(request, timeout=2) as response:
                payload = response.read().decode("utf-8")
        except (OSError, URLError) as exc:
            log_event(
                logger,
                "llm.health.unavailable",
                level=logging.WARNING,
                task="health_check",
                model=self.settings.ollama_model,
                base_url_host=_base_url_host(self.settings.ollama_base_url),
                duration_ms=round((perf_counter() - start) * 1000, 2),
                exception_type=type(exc).__name__,
                message=_truncate(str(exc)),
            )
            return {
                "status": "unavailable",
                "base_url": self.settings.ollama_base_url,
                "model": self.settings.ollama_model,
                "model_available": False,
                "error": str(exc),
            }

        import json

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            log_event(
                logger,
                "llm.health.unavailable",
                level=logging.WARNING,
                task="health_check",
                model=self.settings.ollama_model,
                base_url_host=_base_url_host(self.settings.ollama_base_url),
                duration_ms=round((perf_counter() - start) * 1000, 2),
                exception_type=type(exc).__name__,
                message=_truncate(str(exc)),
            )
            return {
                "status": "unavailable",
                "base_url": self.settings.ollama_base_url,
                "model": self.settings.ollama_model,
                "model_available": False,
                "error": str(exc),
            }

        model_names = {
            model.get("name") or model.get("model")
            for model in data.get("models", [])
            if isinstance(model, dict)
        }
        available = self.settings.ollama_model in model_names
        log_event(
            logger,
            "llm.health.checked",
            level=logging.INFO if available else logging.WARNING,
            task="health_check",
            model=self.settings.ollama_model,
            base_url_host=_base_url_host(self.settings.ollama_base_url),
            model_available=available,
            duration_ms=round((perf_counter() - start) * 1000, 2),
        )
        return {
            "status": "ok" if available else "unavailable",
            "base_url": self.settings.ollama_base_url,
            "model": self.settings.ollama_model,
            "model_available": available,
            **({} if available else {"error": "configured model not found"}),
        }


class FakeLlmClient:
    def __init__(
        self,
        *,
        puzzle_drafts: Sequence[PuzzleDraft | Exception] | None = None,
        topic_interpretations: Sequence[TopicInterpretation | Exception] | None = None,
        core_truths: Sequence[CoreTruthDraft | Exception] | None = None,
        truth_drafts: Sequence[TruthDraft | Exception] | None = None,
        key_facts_drafts: Sequence[KeyFactsDraft | Exception] | None = None,
        surface_story_drafts: Sequence[SurfaceStoryDraft | Exception] | None = None,
        forbidden_assumptions_drafts: Sequence[
            ForbiddenAssumptionsDraft | Exception
        ]
        | None = None,
        review_results: Sequence[PuzzleReviewResult | Exception] | None = None,
        question_judgements: Sequence[QuestionJudgement | Exception] | None = None,
        solution_judgements: Sequence[SolutionJudgement | Exception] | None = None,
    ) -> None:
        self.puzzle_drafts = list(puzzle_drafts or [self.default_puzzle()])
        self.topic_interpretations = list(
            topic_interpretations or [self.default_topic_interpretation()]
        )
        self.core_truths = list(core_truths or [self.default_core_truth()])
        self.truth_drafts = list(truth_drafts or [self.default_truth_draft()])
        self.key_facts_drafts = list(key_facts_drafts or [self.default_key_facts()])
        self.surface_story_drafts = list(
            surface_story_drafts or [self.default_surface_story()]
        )
        self.forbidden_assumptions_drafts = list(
            forbidden_assumptions_drafts or [self.default_forbidden_assumptions()]
        )
        self.review_results = list(review_results or [self.default_review_result()])
        self.question_judgements = list(
            question_judgements
            or [QuestionJudgement(is_valid_question=True, answer="yes")]
        )
        self.solution_judgements = list(
            solution_judgements or [SolutionJudgement(solved=False)]
        )

    @staticmethod
    def default_puzzle() -> PuzzleDraft:
        return PuzzleDraft(
            title="雨夜發票",
            surface_story="雨夜裡，男子撿到一張沒有人認領的發票。隔天，他取消了婚禮。",
            truth="男子原本準備結婚，卻在便利商店發票上看到熟悉的統一編號與品項。那張發票來自未婚妻聲稱早已倒閉的工作室，時間卻是當晚。男子追查後發現未婚妻一直用假身分協助另一人逃避債務，婚禮只是取得財產控制權的安排。他沒有死亡，而是取消婚禮並報警。",
            key_facts=["男子沒有死亡", "發票暴露時間矛盾", "未婚妻隱瞞身分與工作室", "婚禮涉及財產目的"],
            forbidden_assumptions=["男子必然遇害", "發票是中獎發票"],
            difficulty="medium",
        )

    @staticmethod
    def default_topic_interpretation() -> TopicInterpretation:
        return TopicInterpretation(
            title="雨夜發票",
            scene="雨夜的便利商店",
            objects=["發票", "婚禮資料"],
            actors=["男子", "未婚妻"],
            explicit_results=["男子取消婚禮"],
            hard_constraints=["男子沒有死亡", "發票是關鍵物品"],
            open_space="可補充發票如何暴露時間矛盾，但不可加入複雜犯罪或特殊系統。",
        )

    @staticmethod
    def default_core_truth() -> CoreTruthDraft:
        return CoreTruthDraft(
            core_truth="男子在發票時間與品項中發現未婚妻隱瞞行蹤，因此取消婚禮。",
            cause="發票上的時間與品項暴露未婚妻當晚去過她聲稱不會去的地方。",
            actor_action="男子比對發票與未婚妻先前說法。",
            abnormal_result="他隔天取消婚禮。",
            misdirection="玩家容易以為發票本身中獎或牽涉死亡。",
        )

    @staticmethod
    def default_truth_draft() -> TruthDraft:
        return TruthDraft(
            truth=(
                "男子在雨夜撿到的發票不是中獎線索，而是未婚妻當晚購物留下的收據。"
                "發票上的時間與品項和她聲稱在家準備婚禮的說法衝突，也顯示她仍在替已說停用的工作室買材料。"
                "男子隔天到店裡確認監視器，只看到未婚妻自己來付款，沒有危險或死亡事件。"
                "店員也確認那張發票是她結帳後掉在門口的。"
                "他知道問題是對方長期隱瞞行蹤與金錢安排，所以決定取消婚禮。"
            )
        )

    @staticmethod
    def default_key_facts() -> KeyFactsDraft:
        return KeyFactsDraft(
            key_facts=[
                "男子沒有死亡",
                "發票上的時間暴露未婚妻行蹤矛盾",
                "發票品項和未婚妻隱瞞的工作室有關",
                "男子比對說法後取消婚禮",
                "發票不是因為中獎才重要",
            ]
        )

    @staticmethod
    def default_surface_story() -> SurfaceStoryDraft:
        return SurfaceStoryDraft(
            surface_story="雨夜裡，男子撿到一張沒有人認領的發票。隔天，他取消了婚禮。"
        )

    @staticmethod
    def default_forbidden_assumptions() -> ForbiddenAssumptionsDraft:
        return ForbiddenAssumptionsDraft(
            forbidden_assumptions=["男子必然遇害", "發票是中獎發票"]
        )

    @staticmethod
    def default_review_result() -> PuzzleReviewResult:
        return PuzzleReviewResult(passed=True, target_node="finalize_puzzle")

    @staticmethod
    def _pop(queue: list[Any]) -> Any:
        if len(queue) > 1:
            item = queue.pop(0)
        else:
            item = queue[0]
        if isinstance(item, Exception):
            raise item
        return item

    def generate_puzzle(self, topic: str) -> PuzzleDraft:
        log_event(logger, "llm.fake.generate_puzzle", task="generate_puzzle")
        return self._pop(self.puzzle_drafts)

    def interpret_topic(self, topic: str) -> TopicInterpretation:
        log_event(logger, "llm.fake.interpret_topic", task="interpret_topic")
        return self._pop(self.topic_interpretations)

    def generate_core_truth(
        self,
        topic: str,
        interpretation: TopicInterpretation,
        review_instruction: str | None = None,
    ) -> CoreTruthDraft:
        log_event(logger, "llm.fake.generate_core_truth", task="generate_core_truth")
        return self._pop(self.core_truths)

    def expand_truth(
        self,
        topic: str,
        interpretation: TopicInterpretation,
        core_truth: CoreTruthDraft,
        review_instruction: str | None = None,
    ) -> TruthDraft:
        log_event(logger, "llm.fake.expand_truth", task="expand_truth")
        return self._pop(self.truth_drafts)

    def extract_key_facts(self, truth: TruthDraft) -> KeyFactsDraft:
        log_event(logger, "llm.fake.extract_key_facts", task="extract_key_facts")
        return self._pop(self.key_facts_drafts)

    def write_surface_story(
        self,
        topic: str,
        interpretation: TopicInterpretation,
        truth: TruthDraft,
        key_facts: KeyFactsDraft,
        review_instruction: str | None = None,
    ) -> SurfaceStoryDraft:
        log_event(logger, "llm.fake.write_surface_story", task="write_surface_story")
        return self._pop(self.surface_story_drafts)

    def generate_forbidden_assumptions(
        self,
        truth: TruthDraft,
        key_facts: KeyFactsDraft,
        surface_story: SurfaceStoryDraft,
    ) -> ForbiddenAssumptionsDraft:
        log_event(
            logger,
            "llm.fake.generate_forbidden_assumptions",
            task="generate_forbidden_assumptions",
        )
        return self._pop(self.forbidden_assumptions_drafts)

    def review_puzzle(
        self,
        topic: str,
        interpretation: TopicInterpretation,
        core_truth: CoreTruthDraft,
        truth: TruthDraft,
        key_facts: KeyFactsDraft,
        surface_story: SurfaceStoryDraft,
        forbidden_assumptions: list[str],
    ) -> PuzzleReviewResult:
        log_event(logger, "llm.fake.review_puzzle", task="review_puzzle")
        return self._pop(self.review_results)

    def answer_question(
        self,
        puzzle: Puzzle,
        question: str,
        history: list[QuestionRecord],
    ) -> QuestionJudgement:
        log_event(logger, "llm.fake.answer_question", task="answer_question")
        return self._pop(self.question_judgements)

    def judge_solution(
        self,
        puzzle: Puzzle,
        solution: str,
        history: list[QuestionRecord],
    ) -> SolutionJudgement:
        log_event(logger, "llm.fake.judge_solution", task="judge_solution")
        return self._pop(self.solution_judgements)

    def health_check(self) -> dict[str, object]:
        log_event(logger, "llm.fake.health_check", task="health_check")
        return {
            "status": "ok",
            "base_url": "fake://ollama",
            "model": "fake",
            "model_available": True,
        }


def _base_url_host(base_url: str) -> str:
    parsed = urlparse(base_url)
    return parsed.netloc or parsed.path


def _prompt_summary(messages: list[SystemMessage | HumanMessage]) -> dict[str, int]:
    system_chars = 0
    human_chars = 0
    for message in messages:
        content = message.content if isinstance(message.content, str) else str(message.content)
        if isinstance(message, SystemMessage):
            system_chars += len(content)
        else:
            human_chars += len(content)
    return {"system_chars": system_chars, "human_chars": human_chars}


def _truncate(message: str, max_chars: int = 240) -> str:
    normalized = " ".join(message.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[:max_chars] + "..."


def _raw_response_payload(response: Any) -> Any:
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    if hasattr(response, "dict"):
        return response.dict()
    return response
