import json

from app.errors import ApiErrorCode, AppError, error_response


def test_error_response_uses_unified_shape() -> None:
    response = error_response(AppError(ApiErrorCode.INVALID_QUESTION, status_code=400))

    assert response.status_code == 400
    assert json.loads(response.body) == {
        "error": {
            "code": "INVALID_QUESTION",
            "message": "請輸入可用是／否回答的問題",
        }
    }
