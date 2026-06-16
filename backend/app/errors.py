from __future__ import annotations

from enum import StrEnum

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ApiErrorCode(StrEnum):
    GAME_NOT_FOUND = "GAME_NOT_FOUND"
    GAME_ALREADY_ENDED = "GAME_ALREADY_ENDED"
    INVALID_QUESTION = "INVALID_QUESTION"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    LLM_OUTPUT_INVALID = "LLM_OUTPUT_INVALID"
    STORAGE_ERROR = "STORAGE_ERROR"


DEFAULT_MESSAGES: dict[ApiErrorCode, str] = {
    ApiErrorCode.GAME_NOT_FOUND: "找不到遊戲",
    ApiErrorCode.GAME_ALREADY_ENDED: "遊戲已結束，不能繼續操作",
    ApiErrorCode.INVALID_QUESTION: "請輸入可用是／否回答的問題",
    ApiErrorCode.LLM_UNAVAILABLE: "Ollama 或模型目前不可用",
    ApiErrorCode.LLM_OUTPUT_INVALID: "模型輸出無法解析，請稍後再試",
    ApiErrorCode.STORAGE_ERROR: "遊戲紀錄讀寫失敗",
}


class ErrorBody(BaseModel):
    code: ApiErrorCode
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class AppError(Exception):
    def __init__(
        self,
        code: ApiErrorCode,
        message: str | None = None,
        status_code: int = 400,
    ) -> None:
        self.code = code
        self.message = message or DEFAULT_MESSAGES[code]
        self.status_code = status_code
        super().__init__(self.message)


def error_response(error: AppError) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=error.code, message=error.message))
    return JSONResponse(
        status_code=error.status_code,
        content=body.model_dump(mode="json"),
    )


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return error_response(exc)
