from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, TypeVar
from urllib.error import URLError
from urllib.request import Request, urlopen

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


T = TypeVar("T", bound=BaseModel)


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
        schema: type[T],
        messages: list[SystemMessage | HumanMessage],
        temperature: float,
    ) -> T:
        last_error: Exception | None = None
        attempts = (
            self.settings.llm.request_max_retries
            + self.settings.llm.structured_output_max_retries
            + 1
        )
        for _ in range(attempts):
            try:
                model = self._chat(temperature).with_structured_output(schema)
                result = model.invoke(messages)
                if isinstance(result, schema):
                    return result
                return schema.model_validate(result)
            except ValidationError as exc:
                last_error = exc
            except Exception as exc:
                last_error = exc
                message = str(exc).lower()
                if any(token in message for token in ("connection", "timeout", "refused")):
                    continue
        code = ApiErrorCode.LLM_OUTPUT_INVALID
        if last_error and any(
            token in str(last_error).lower()
            for token in ("connection", "timeout", "refused", "unavailable")
        ):
            code = ApiErrorCode.LLM_UNAVAILABLE
        raise AppError(code, status_code=503 if code == ApiErrorCode.LLM_UNAVAILABLE else 500)

    def generate_puzzle(self, topic: str) -> PuzzleDraft:
        return self._invoke_structured(
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
            SolutionJudgement,
            [
                SystemMessage(content=judge_solution_system_prompt()),
                HumanMessage(content=judge_solution_user_prompt(puzzle, solution, history)),
            ],
            self.settings.llm.judge_temperature,
        )

    def health_check(self) -> dict[str, object]:
        tags_url = self.settings.ollama_base_url.rstrip("/") + "/api/tags"
        try:
            request = Request(tags_url, headers={"Accept": "application/json"})
            with urlopen(request, timeout=2) as response:
                payload = response.read().decode("utf-8")
        except (OSError, URLError) as exc:
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
        return self._pop(self.puzzle_drafts)

    def answer_question(
        self,
        puzzle: Puzzle,
        question: str,
        history: list[QuestionRecord],
    ) -> QuestionJudgement:
        return self._pop(self.question_judgements)

    def judge_solution(
        self,
        puzzle: Puzzle,
        solution: str,
        history: list[QuestionRecord],
    ) -> SolutionJudgement:
        return self._pop(self.solution_judgements)

    def health_check(self) -> dict[str, object]:
        return {
            "status": "ok",
            "base_url": "fake://ollama",
            "model": "fake",
            "model_available": True,
        }
