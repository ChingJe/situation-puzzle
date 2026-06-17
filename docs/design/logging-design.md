# Logging 與可觀察性設計

## 目的

目前專案已能完成基本遊戲流程，但缺少一致的 log 機制，導致開發者難以判斷：

- API request 是否進入正確 endpoint。
- GameService 狀態轉移是否符合預期。
- LangGraph 節點是否被執行，以及執行順序與耗時。
- LLM provider request 是否送出、是否 timeout、structured output 是否重試。
- storage 是否成功寫入或讀取歷史紀錄。
- WSL、Windows 端 LLM runtime、模型設定等環境問題發生在哪一層。

本文件定義第一版 logging 設計，目標是讓本地開發時可以快速定位問題。此專案假設後端 log 是開發者觀測工具，不把「玩家主動翻 log 看到答案」視為需要防範的主要情境。

## 設計目標

- 使用 Python 標準 `logging` 為主，不引入大型 observability stack。
- 後端 log 採結構化 JSON lines，方便日後 grep、jq、匯入其他工具。
- 每個 API request 有 `request_id`，每局遊戲有 `game_id`，每次 LLM 呼叫有 `llm_call_id`。
- 能觀察 agent 工作流程：graph node start/end、LLM task、retry、validation error、耗時。
- structured event log 以事件摘要、狀態、耗時為主，避免太吵。
- raw message log 可以完整保存玩家 request、LLM prompt、provider raw response 與 parsed output，作為本機除錯主要依據。
- 前端顯示一般錯誤訊息即可，詳細除錯資訊留在後端 log。

## 非目標

第一版不做：

- OpenTelemetry tracing。
- Prometheus metrics。
- ELK、Loki、Grafana 等外部服務。
- 前端遠端 log 上報。
- 將完整 prompt 與完整 LLM raw output 上傳到外部服務或作為 production 長期稽核資料保存。
- 在瀏覽器 UI 顯示後端 debug trace。

這些可在核心流程穩定後再評估。

## Log 形式

後端使用 JSON lines，每行一筆 event。

範例：

```json
{
  "ts": "2026-06-16T13:20:00.123+08:00",
  "level": "INFO",
  "logger": "app.services.game_service",
  "event": "game.created",
  "request_id": "req_01JZ...",
  "game_id": "9b5f...",
  "duration_ms": 18420,
  "status": "playing"
}
```

欄位規則：

- `ts`：ISO 8601，包含 timezone offset。
- `level`：`DEBUG | INFO | WARNING | ERROR | CRITICAL`。
- `logger`：Python logger name，例如 `app.llm.client`。
- `event`：穩定事件名稱，使用 dot notation。
- `request_id`：每個 HTTP request 產生一個。
- `game_id`：建立遊戲後開始出現。
- `llm_call_id`：每次 LLM task 產生一個。
- `duration_ms`：有耗時的事件必填。
- `error_code`：若對應 `ApiErrorCode`，記錄 enum 字串。
- `exception_type`：捕捉 exception 時記錄 class name。

## Log Level

### DEBUG

只在開發除錯時使用。

可記錄：

- graph state key 列表。
- prompt 長度、玩家輸入長度、LLM output 長度。
- structured output retry 次數。
- validation error 摘要。

一般 structured event log 不建議記錄：

- 完整 `truth`。
- 完整 `key_facts`。
- 完整 prompt。
- 完整 raw LLM output。

這不是為了避免玩家暴雷，而是為了讓 `logs/app.log` 保持可掃描。完整內容由 raw message log 負責。

### INFO

預設開發 level。

記錄：

- API request start/end。
- game created、question answered、solution judged、game finalized。
- LLM task start/end。
- storage read/write success。
- health check result summary。

### WARNING

可恢復但需要注意的狀況。

記錄：

- invalid question。
- structured output 第一次失敗後 retry。
- history 中發現損壞 JSON 並跳過。
- selected LLM model not found，health degraded。

### ERROR

使用者操作失敗或系統行為未完成。

記錄：

- `LLM_UNAVAILABLE`。
- `LLM_OUTPUT_INVALID`。
- storage write/read failure。
- 未預期 exception。

## Logger 分層

建議 logger name：

- `app.main`
- `app.middleware.request`
- `app.routes.games`
- `app.routes.history`
- `app.services.game_service`
- `app.graph.workflow`
- `app.graph.nodes`
- `app.llm.client`
- `app.storage`
- `app.health`

模組責任：

- middleware 負責 request_id、request start/end、HTTP status、duration。
- route 只記錄 endpoint 層的簡短事件，不記 domain 細節。
- service 記錄 game lifecycle 與狀態轉移。
- graph 記錄節點執行順序與結果類型。
- llm client 記錄模型、task、retry、耗時、錯誤分類。
- storage 記錄檔案讀寫結果與錯誤。
- health 記錄環境狀態摘要。

## Request Correlation

新增 middleware：

1. 讀取 request header `X-Request-ID`。
2. 若不存在，產生新的 request id。
3. 使用 `contextvars` 保存 request id。
4. response header 回傳 `X-Request-ID`。
5. 所有 log 自動帶上 request id。

建議格式：

```text
req_{uuid4_hex}
```

在同一 request 內：

- `POST /api/games` 的所有 graph 與 LLM log 都帶同一個 `request_id`。
- 建立 `game_id` 後，後續 log 同時帶 `request_id` 與 `game_id`。

## Game Event

GameService 應記錄以下事件。

### `game.create.started`

level：INFO

欄位：

- `topic_length`
- `active_session_count`

不可記錄完整 topic，除非 debug 且啟用 safe preview。

### `game.created`

level：INFO

欄位：

- `game_id`
- `title`
- `surface_story_length`
- `difficulty`
- `duration_ms`

不記錄：

- `truth`
- `key_facts`
- `forbidden_assumptions`

### `question.answer.started`

level：INFO

欄位：

- `game_id`
- `question_length`
- `question_count_before`

### `question.answered`

level：INFO

欄位：

- `game_id`
- `answer`
- `question_count_after`
- `duration_ms`

### `question.invalid`

level：WARNING

欄位：

- `game_id`
- `question_length`
- `error_code`: `INVALID_QUESTION`

### `solution.judge.started`

level：INFO

欄位：

- `game_id`
- `solution_length`
- `attempt_count_before`

### `solution.judged`

level：INFO

欄位：

- `game_id`
- `solved`
- `status`
- `attempt_count_after`
- `duration_ms`

### `game.abandoned`

level：INFO

欄位：

- `game_id`
- `question_count`
- `attempt_count`

### `game.finalized`

level：INFO

欄位：

- `game_id`
- `status`
- `ended_at`
- `storage_path`
- `duration_ms`

## LangGraph Event

Graph workflow 應記錄：

- `graph.invoke.started`
- `graph.invoke.finished`
- `graph.node.started`
- `graph.node.finished`
- `graph.node.failed`

欄位：

- `workflow`: `generate_puzzle_pipeline | answer_question | judge_solution`
- `node`
- `game_id`，若已有
- `duration_ms`
- `state_keys`

不記錄完整 state。state 可能包含 `Puzzle.truth`，因此只能記 key 名稱與長度摘要。

題目生成 pipeline 應額外記錄 `revision_count`、`review_passed`、`review_target_node` 與 `issue_count`，方便追蹤 reviewer 為何要求重寫。

## LLM Event

LLM client 應記錄每次 task。

Task 類型：

- `interpret_topic`
- `generate_core_truth`
- `expand_truth`
- `extract_solution_facts`
- `write_surface_story`
- `generate_assumptions`
- `review_puzzle`
- `finalize_puzzle`
- `answer_question`
- `judge_solution`
- `health_check`

### `llm.call.started`

level：INFO

欄位：

- `llm_call_id`
- `task`
- `model`
- `base_url_host`
- `temperature`
- `request_timeout_seconds`

`base_url_host` 只記 host 與 port，例如 `192.168.192.1:11434`，避免將完整 URL 當作敏感設定擴散。

### `llm.call.finished`

level：INFO

欄位：

- `llm_call_id`
- `task`
- `duration_ms`
- `output_schema`
- `retry_count`

### `llm.call.retry`

level：WARNING

欄位：

- `llm_call_id`
- `task`
- `retry_index`
- `retry_reason`: `request_error | validation_error`
- `exception_type`
- `message`

`message` 需截斷到固定長度。

### `llm.call.failed`

level：ERROR

欄位：

- `llm_call_id`
- `task`
- `error_code`: `LLM_UNAVAILABLE | LLM_OUTPUT_INVALID`
- `retry_count`
- `duration_ms`

## Prompt 與 Output 記錄策略

第一版將 log 分成兩種：

- structured event log：預設開啟，寫入 `logs/app.log`，記錄事件、狀態、耗時、長度摘要，不寫完整內容。
- raw message log：寫入 `logs/messages.log`，可記錄完整玩家輸入、agent prompt、LLM provider raw response、parsed structured output。

structured event log 不記完整 prompt 或 raw output，完整內容統一進 raw message log。

可記錄摘要：

```json
{
  "prompt_summary": {
    "system_chars": 420,
    "human_chars": 980,
    "history_count": 8
  },
  "output_summary": {
    "schema": "QuestionJudgement",
    "valid": true
  }
}
```

若需要 debug prompt，可加 config：

```toml
[logging]
log_prompt_preview = false
prompt_preview_chars = 160
log_llm_output_preview = false
llm_output_preview_chars = 160
```

即使開啟 preview，也只允許記錄：

- 使用者 topic preview。
- 使用者 question preview。
- 使用者 solution preview。
- surface story preview。

structured event log 不記錄：

- 完整 truth。
- key facts 列表內容。
- forbidden assumptions 內容。

上述規則只適用於 structured event log。raw message log 可以保存這些內容，因為生成題目與判定流程需要看到完整 agent/LLM provider 互動才能除錯。

## Raw Message Log

raw message log 用於觀察「玩家輸入 -> agent prompt -> LLM provider raw response -> parsed output」的完整資料流。這類 log 對調整 prompt、debug structured output、判斷模型是否照規則回答非常重要，因此應完整保存足夠資訊。

### 基本規則

- 開發環境預設建議開啟。
- 只作為本機開發觀測資料使用。
- 不輸出到 console。
- 不進 git。
- 使用獨立檔案 `logs/messages.log`。
- 每筆 raw message 必須帶 `request_id`。
- 若已建立遊戲，必須帶 `game_id`。
- 每次 LLM 呼叫必須帶 `llm_call_id`。
- 每筆 raw message 必須有 `message_kind` 與 `task`。

### Mode

建議用 `raw_message_mode` 控制：

```text
off
preview
full
```

- `off`：不記 raw message，僅在需要減少磁碟輸出或正式部署時使用。
- `preview`：記錄截斷內容，方便看大致輸入輸出，但不保存完整謎底。
- `full`：記錄完整內容，包含 hidden puzzle data、完整 prompt、LLM provider raw response 與 parsed output。

本機開發預設建議使用 `full`。若未來有部署環境，再把部署環境預設改為 `off` 或 `preview`。

### Raw Message Event

使用 JSON lines，每行一筆。

欄位：

- `ts`
- `level`
- `logger`
- `event`: 固定為 `raw.message`
- `request_id`
- `game_id`，若已有
- `llm_call_id`，若是 LLM 相關
- `message_kind`
- `task`
- `mode`
- `content_type`
- `content`
- `content_chars`
- `truncated`

`message_kind` 建議值：

- `http.request.body`
- `player.topic`
- `player.question`
- `player.solution`
- `llm.system_prompt`
- `llm.human_prompt`
- `llm.raw_response`
- `llm.parsed_output`
- `agent.decision`

`task` 建議值：

- `create_game`
- `ask_question`
- `submit_solution`
- `abandon_game`
- `generate_puzzle_pipeline`
- `interpret_topic`
- `generate_core_truth`
- `expand_truth`
- `extract_solution_facts`
- `write_surface_story`
- `generate_assumptions`
- `review_puzzle`
- `answer_question`
- `judge_solution`
- `history`
- `health_check`

### 範例

玩家建立題目：

```json
{
  "ts": "2026-06-16T13:25:00.123+08:00",
  "level": "DEBUG",
  "logger": "app.raw_messages",
  "event": "raw.message",
  "request_id": "req_abc",
  "message_kind": "player.topic",
  "task": "create_game",
  "mode": "full",
  "content_type": "text",
  "content": "雨夜、便利商店、一張沒有人認領的發票",
  "content_chars": 21,
  "truncated": false
}
```

LLM prompt：

```json
{
  "ts": "2026-06-16T13:25:01.000+08:00",
  "level": "DEBUG",
  "logger": "app.raw_messages",
  "event": "raw.message",
  "request_id": "req_abc",
  "llm_call_id": "llm_def",
  "message_kind": "llm.human_prompt",
  "task": "generate_core_truth",
  "mode": "full",
  "content_type": "text",
  "content": "玩家提供的主題如下...",
  "content_chars": 430,
  "truncated": false
}
```

Final puzzle decision：

```json
{
  "ts": "2026-06-16T13:25:20.000+08:00",
  "level": "DEBUG",
  "logger": "app.raw_messages",
  "event": "raw.message",
  "request_id": "req_abc",
  "game_id": "9b5f...",
  "message_kind": "agent.decision",
  "task": "generate_puzzle_pipeline",
  "mode": "full",
  "content_type": "json",
  "content": {
    "title": "雨夜發票",
    "surface_story": "...",
    "truth": "...",
    "key_facts": ["..."],
    "forbidden_assumptions": ["..."],
    "difficulty": "medium"
  },
  "content_chars": 720,
  "truncated": false
}
```

### 記錄點

GameService：

- `create_game(topic)` 記錄 `player.topic`。
- `ask_question(question)` 記錄 `player.question`。
- `submit_solution(solution)` 記錄 `player.solution`。

LLM client：

- invoke 前記錄 `llm.system_prompt`。
- invoke 前記錄 `llm.human_prompt`。
- invoke 後若能取得 raw response，記錄 `llm.raw_response`。
- structured output 驗證成功後，記錄 `llm.parsed_output`。
- structured output 驗證失敗時，記錄失敗的 raw response 或 exception 摘要。

API middleware：

- 第一版不建議 middleware 全量記錄 request body，避免破壞 streaming/body read 流程。
- 若未來需要記錄 HTTP raw body，應在 route 或 service 層記錄已解析後的 request model。

### 操作提醒

`raw_message_mode = "full"` 會保存：

- 完整玩家主題、問題、解答。
- 完整 prompt。
- 完整模型輸出。
- 完整謎底。
- key facts。
- forbidden assumptions。

因此：

- 不得 commit `logs/messages.log`。
- raw message log 應視為本機除錯資料。
- 若要分享 log，應先確認內容是否適合外流，或改用 `preview` 模式重現問題。

## Storage Event

Storage layer 應記錄：

- `storage.ensure_ready`
- `storage.write.started`
- `storage.write.finished`
- `storage.read.started`
- `storage.read.finished`
- `storage.history_list.finished`
- `storage.corrupt_file_skipped`
- `storage.failed`

欄位：

- `game_id`
- `path`
- `record_count`
- `duration_ms`
- `exception_type`

`path` 可記相對於專案根目錄的 path，例如 `data/games/{game_id}.json`。

## Health 與環境 Event

Health check 應記錄：

- `health.checked`
- `health.llm.unavailable`
- `health.storage.unavailable`

欄位：

- `overall_status`
- `llm_provider`
- `llm_status`
- `llm_model`
- `llm_model_available`
- `storage_status`
- `storage_writable`

WSL + Windows 端 LLM runtime 特別需要看：

- `llm_base_url_host`
- model name
- connection error message

## API Request Log

Middleware 記錄：

### `http.request.started`

level：INFO

欄位：

- `method`
- `path`
- `client_host`

### `http.request.finished`

level：INFO 或 ERROR

欄位：

- `method`
- `path`
- `status_code`
- `duration_ms`
- `error_code`，若有

不可記錄：

- request body。
- response body。

如需除錯 body，應由 service/LLM 層用長度或 preview 策略記錄，而非 middleware 全量記錄。

## Frontend Logging

第一版前端只做 local debug，不上報。

建議：

- API client 捕捉 error 時在 browser console 記錄：
  - endpoint
  - HTTP status
  - API error code
  - request id response header
- UI 顯示使用者可理解的錯誤訊息。
- 不在 UI 顯示 stack trace。

未來可增加「開發者面板」：

- 顯示最近 API calls。
- 顯示 `X-Request-ID`。
- 可複製 request id 回後端 log 查詢。

第一版先不實作開發者面板。

## Config 設計

新增 `config.toml`：

```toml
[logging]
level = "INFO"
format = "json"
log_dir = "logs"
file_enabled = true
console_enabled = true
max_file_mb = 10
backup_count = 5
log_prompt_preview = false
prompt_preview_chars = 160
log_llm_output_preview = false
llm_output_preview_chars = 160
raw_message_mode = "full"
raw_message_log_file = "logs/messages.log"
raw_message_max_chars = 20000
raw_message_include_player_messages = true
raw_message_include_llm_prompts = true
raw_message_include_llm_responses = true
raw_message_include_parsed_outputs = true
```

新增 `.env` 可覆蓋：

```env
LOG_LEVEL=INFO
```

分工：

- `config.toml`：log 格式、檔案路徑、rotation、preview/raw message 行為。本機開發預設可使用完整 raw message log。
- `.env`：每台機器可能不同的 log level。

## 檔案輸出

預設輸出：

```text
logs/app.log
```

格式：JSON lines。

若啟用 raw message log，額外輸出：

```text
logs/messages.log
```

`logs/app.log` 用於查事件與耗時；`logs/messages.log` 用於查完整玩家 request、agent prompt、LLM provider response 與 parsed output。

rotation：

- 單檔最大 10 MB。
- 保留 5 個備份。

`.gitignore` 應加入：

```gitignore
logs/*.log
logs/*.log.*
```

保留 `logs/.gitkeep` 可選，不必第一版建立。

## 實作模組

建議新增：

```text
backend/app/logging_config.py
backend/app/middleware.py
backend/tests/test_logging.py
```

`logging_config.py`：

- 讀取 settings。
- 設定 root logger。
- 設定 JSON formatter。
- 設定 console handler。
- 設定 rotating file handler。
- 設定 raw message handler。
- 注入 context fields。

`middleware.py`：

- request id middleware。
- request start/end logging。
- response header `X-Request-ID`。

可選 helper：

```text
backend/app/observability.py
```

用途：

- `get_request_id()`
- `set_game_id()`
- `safe_preview()`
- `log_event(logger, event, **fields)`
- `log_raw_message(kind, task, content, **fields)`

## 測試策略

後端測試：

- middleware 會為 response 加上 `X-Request-ID`。
- 若 request 帶 `X-Request-ID`，response 沿用。
- API error log 包含 `error_code`。
- GameService create/ask/submit 會產生預期 event。
- LLM fake retry 可產生 `llm.call.retry`。
- structured output failure 會產生 `LLM_OUTPUT_INVALID` log。
- storage corrupt JSON 會產生 warning log。
- structured event log 不包含 `truth`、`key_facts` 內容。
- raw message 本機開發預設開啟。
- raw message `preview` 模式會截斷內容。
- raw message `full` 模式可記錄完整玩家輸入、LLM prompt、provider output 與 parsed output。

測試工具：

- pytest `caplog`。
- temporary log directory。
- fake LLM。

前端：

- 第一版仍只做 `npm run build`。

## 開發驗收流程

1. 啟動後端：

```bash
make dev-backend
```

2. 建立一局遊戲。
3. 提問一次有效問題。
4. 提問一次無效問題。
5. 提交一次錯誤解答。
6. 放棄或成功解開。
7. 檢查 `logs/app.log`：
   - 能以 `request_id` 串起 API request 與 LLM call。
   - 能以 `game_id` 找到同一局所有事件。
   - 能看到 LLM task 耗時與 retry。
   - event log 仍保持摘要化，適合快速掃描。
8. 檢查 `logs/messages.log`：
   - 能以同一個 `request_id` 串起玩家輸入與 LLM 呼叫。
   - 能以同一個 `llm_call_id` 找到 prompt、raw response、parsed output。
   - 能看到完整 LLM provider 回覆，用於 debug structured output。

範例查詢：

```bash
rg '"game_id":"<game_id>"' logs/app.log
rg '"event":"llm.call.retry"' logs/app.log
rg '"llm_call_id":"<llm_call_id>"' logs/messages.log
```

若安裝 `jq`：

```bash
jq 'select(.game_id == "<game_id>")' logs/app.log
jq 'select(.level == "ERROR")' logs/app.log
jq 'select(.llm_call_id == "<llm_call_id>")' logs/messages.log
```

## 實作順序

1. 新增 logging config schema 與 `config.toml` logging section。
2. 實作 JSON formatter、contextvars、request id middleware。
3. 在 FastAPI app startup 初始化 logging。
4. 在 middleware 記錄 request start/end。
5. 在 GameService 增加 lifecycle log。
6. 在 graph workflow/node 增加 node start/end log。
7. 在 LLM client 增加 call/retry/failure log。
8. 在 storage 與 health 增加環境與讀寫 log。
9. 實作 raw message logger 與 `logs/messages.log`，本機開發預設 full。
10. 在 GameService 記錄玩家 raw message。
11. 在 LLM client 記錄 prompt、raw response、parsed output。
12. 補 pytest `caplog` 與 temporary log file 測試。
13. 更新 README 開發除錯章節。

## 後續擴充

- 增加 `/api/debug/logs/recent`，只在 development mode 啟用。
- 增加前端開發者面板，顯示最近 API request id。
- 整合 LangChain callback handler，取得更細的 LLM token 與 tool event。
- 整合 OpenTelemetry。
- 增加 metrics：LLM latency、structured output failure rate、storage error count。
