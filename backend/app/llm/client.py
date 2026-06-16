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
    judge_solution_system_prompt,
    judge_solution_user_prompt,
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
from app.observability import bind_log_context, log_event, log_raw_message


T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger("app.llm.client")


class LlmClient(Protocol):
    def generate_puzzle(self, topic: str) -> PuzzleDraft: ...

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
        question_judgements: Sequence[QuestionJudgement | Exception] | None = None,
        solution_judgements: Sequence[SolutionJudgement | Exception] | None = None,
    ) -> None:
        self.puzzle_drafts = list(puzzle_drafts or [self.default_puzzle()])
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
