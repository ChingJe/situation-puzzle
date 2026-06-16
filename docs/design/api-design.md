# API 設計

## 基本規則

- API 使用 REST。
- 所有 request/response 使用 JSON。
- 遊戲進行中不回傳 `truth`、`key_facts`、`forbidden_assumptions`。
- 遊戲結束後，歷史紀錄與結束回應可以回傳完整真相。
- 錯誤回應使用統一格式。

## 統一錯誤格式

```json
{
  "error": {
    "code": "INVALID_QUESTION",
    "message": "請輸入可用是／否回答的問題"
  }
}
```

## 錯誤碼

- `GAME_NOT_FOUND`：找不到遊戲。
- `GAME_ALREADY_ENDED`：遊戲已結束，不能繼續操作。
- `INVALID_QUESTION`：玩家輸入不是可用是／否回答的問題。
- `LLM_UNAVAILABLE`：目前選定的 LLM provider、runtime 或模型不可用。
- `LLM_OUTPUT_INVALID`：模型輸出無法通過 structured output 驗證。
- `STORAGE_ERROR`：JSON 紀錄讀寫失敗。

## Health Check

### `GET /api/health`

檢查後端、目前選定的 LLM provider、模型與儲存目錄狀態。LLM runtime 不可用時不阻止後端啟動，但狀態應回傳 `degraded`。

LLM health response 使用通用 `llm` 區塊，避免 API schema 綁死在單一 runtime。第一版正式支援的 provider：

- `ollama`：呼叫 Ollama API，例如 `http://localhost:11434`。
- `openai-compatible`：呼叫 OpenAI-compatible API，例如 llama.cpp server 的 `http://<host>:18080/v1`。

成功範例：

```json
{
  "status": "ok",
  "backend": {
    "status": "ok"
  },
  "llm": {
    "status": "ok",
    "provider": "openai-compatible",
    "base_url": "http://192.168.192.1:18080/v1",
    "model": "qwen3.6-35b-a3b",
    "model_available": true
  },
  "storage": {
    "status": "ok",
    "games_dir": "data/games",
    "writable": true
  }
}
```

降級範例：

```json
{
  "status": "degraded",
  "backend": {
    "status": "ok"
  },
  "llm": {
    "status": "unavailable",
    "provider": "openai-compatible",
    "base_url": "http://192.168.192.1:18080/v1",
    "model": "qwen3.6-35b-a3b",
    "model_available": false,
    "error": "connection refused"
  },
  "storage": {
    "status": "ok",
    "games_dir": "data/games",
    "writable": true
  }
}
```

## 建立遊戲

### `POST /api/games`

Request:

```json
{
  "topic": "雨夜、便利商店、一張沒有人認領的發票"
}
```

Response:

```json
{
  "game_id": "01JZ...",
  "surface_story": "某個雨夜，一名男子在便利商店撿到一張發票。隔天，他再也沒有回家。",
  "status": "playing"
}
```

## 取得進行中遊戲

### `GET /api/games/{game_id}`

用於前端刷新後恢復仍在後端記憶體中的遊戲。

Response:

```json
{
  "game_id": "01JZ...",
  "topic": "雨夜、便利商店、一張沒有人認領的發票",
  "surface_story": "某個雨夜，一名男子在便利商店撿到一張發票。隔天，他再也沒有回家。",
  "status": "playing",
  "questions": [
    {
      "question": "男子死亡了嗎？",
      "answer": "yes",
      "display_answer": "是",
      "created_at": "2026-06-16T11:00:00+08:00"
    }
  ],
  "solution_attempts": []
}
```

## 提問

### `POST /api/games/{game_id}/questions`

Request:

```json
{
  "question": "男子死亡了嗎？"
}
```

Response:

```json
{
  "answer": "yes",
  "display_answer": "是"
}
```

若問題不是可用是／否回答的問題：

```json
{
  "error": {
    "code": "INVALID_QUESTION",
    "message": "請輸入可用是／否回答的問題"
  }
}
```

## 提交解答

### `POST /api/games/{game_id}/solution`

Request:

```json
{
  "solution": "我認為男子發現那張發票證明某個人還活著，因此回去調查時遇害。"
}
```

未解開 response:

```json
{
  "solved": false,
  "message": "尚未解開",
  "status": "playing"
}
```

解開 response:

```json
{
  "solved": true,
  "message": "成功解開",
  "status": "solved",
  "truth": "完整真相..."
}
```

## 放棄遊戲

### `POST /api/games/{game_id}/abandon`

Response:

```json
{
  "status": "abandoned",
  "truth": "完整真相..."
}
```

放棄後應寫入歷史 JSON 紀錄。

## 歷史列表

### `GET /api/history`

Response:

```json
{
  "items": [
    {
      "game_id": "01JZ...",
      "title": "雨夜發票",
      "topic": "雨夜、便利商店、一張沒有人認領的發票",
      "status": "solved",
      "question_count": 12,
      "created_at": "2026-06-16T11:00:00+08:00",
      "ended_at": "2026-06-16T11:20:00+08:00"
    }
  ]
}
```

## 歷史詳情

### `GET /api/history/{game_id}`

回傳完整已結束遊戲紀錄，包含真相、問答與提交解答紀錄。
