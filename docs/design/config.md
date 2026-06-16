# 設定管理

## 分工

設定採用 `.env` 與 `config.toml` 混合。

`.env` 負責環境相關、不同機器會變的值，不進 git。

`config.toml` 負責應用行為參數，可以進 git。

環境變數可以覆蓋 `.env`。

## 載入順序

1. 讀取 `config.toml`。
2. 讀取 `.env`。
3. 套用系統環境變數覆蓋。
4. 建立後端 `Settings` 物件。

## `.env`

範例檔案應提供 `.env.example`。

```env
LLM_PROVIDER=openai-compatible
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma4:e4b
OPENAI_COMPATIBLE_BASE_URL=http://localhost:18080/v1
OPENAI_COMPATIBLE_MODEL=qwen3.6-35b-a3b
```

欄位：

- `LLM_PROVIDER`：LLM runtime 類型。建議值：`ollama` 或 `openai-compatible`。
- `OLLAMA_BASE_URL`：Ollama API base URL。
- `OLLAMA_MODEL`：Ollama 模型名稱。
- `OPENAI_COMPATIBLE_BASE_URL`：OpenAI-compatible API base URL，例如 llama.cpp server 的 `/v1` endpoint。
- `OPENAI_COMPATIBLE_MODEL`：OpenAI-compatible API 使用的模型名稱。

預設題目生成 runtime 為 `openai-compatible + qwen3.6-35b-a3b`。WSL 連線 Windows 端 llama.cpp 時，`OPENAI_COMPATIBLE_BASE_URL` 通常需使用 Windows gateway IP，例如 `http://192.168.192.1:18080/v1`，不可假設 `localhost` 一定可用。

Provider 選擇規則：

- `LLM_PROVIDER=ollama` 時，後端只使用 `OLLAMA_BASE_URL` 與 `OLLAMA_MODEL`。
- `LLM_PROVIDER=openai-compatible` 時，後端只使用 `OPENAI_COMPATIBLE_BASE_URL` 與 `OPENAI_COMPATIBLE_MODEL`。
- 未選中的 provider 設定可以保留在 `.env` 中，方便切換，但 health check 與正式遊戲流程只檢查目前選中的 provider。
- 後端啟動時不因 provider unavailable 直接失敗；建立遊戲、提問或判定解答時若 provider 不可用，才回傳 `LLM_UNAVAILABLE`。
- `.env.example` 應以 `LLM_PROVIDER=openai-compatible` 作為預設範例，Ollama 欄位則作為保留的替代 runtime 設定。

## `config.toml`

```toml
[llm]
request_timeout_seconds = 600
request_max_retries = 2
structured_output_max_retries = 2
generation_temperature = 0.8
answer_temperature = 0.1
judge_temperature = 0.1
openai_compatible_max_tokens = 0

[puzzle]
surface_story_max_chars = 150
truth_min_chars = 300
truth_max_chars = 800
key_facts_min = 4
key_facts_max = 8
language = "zh-TW"
content_style = "懸疑、適合一般玩家、避免露骨血腥描寫"

[puzzle_generation]
reviewer_enabled = true
deterministic_gate_enabled = true
max_revision_rounds = 2
strict_surface_story_max_chars = 120
strict_truth_min_chars = 160
strict_truth_max_chars = 280

[storage]
data_dir = "data"
games_dir = "data/games"

[api]
cors_origins = ["http://localhost:5173"]

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

## LLM 設定

- `request_timeout_seconds`：每次 LLM request timeout。若使用 `qwen3.6-35b-a3b` 生成題目，建議至少 `600` 秒。
- `request_max_retries`：連線、timeout、5xx 等 request retry 次數。
- `structured_output_max_retries`：模型輸出不符合 schema 時的 retry 次數。
- `generation_temperature`：題目生成溫度，預設 `0.8`。
- `answer_temperature`：是非題判定溫度，預設 `0.1`。
- `judge_temperature`：解答判定溫度，預設 `0.1`。
- `openai_compatible_max_tokens`：OpenAI-compatible request 的 `max_tokens`。`0` 表示不傳此欄位；目前 Qwen 測試中若限制過低，reasoning 會消耗 token 並截斷 JSON content，因此建議保持 `0`。

題目生成速度與品質的目前決策：

- `qwen3.6-35b-a3b` 完整 pipeline 約 10 分鐘，但可產生較合理、可玩的核心題目。
- 此模型與 llama.cpp OpenAI-compatible API 是後續正式預設。
- 此速度在目前產品定位中可接受，因為生成發生在開局前，且品質比即時性更重要。
- UI/API 後續可考慮顯示生成中狀態，但不應為了縮短生成時間犧牲題目品質。

## Puzzle 設定

- `surface_story_max_chars`：謎面最大字數。
- `truth_min_chars`：真相最少字數。
- `truth_max_chars`：真相最多字數。
- `key_facts_min`：關鍵事實最少條數。
- `key_facts_max`：關鍵事實最多條數。
- `language`：生成語言，第一版固定 `zh-TW`。
- `content_style`：題材與內容風格限制。

`[puzzle]` 保留為正式 `Puzzle` schema 的一般限制。題目生成 pipeline 可以使用 `[puzzle_generation]` 的更嚴格限制，以避免模型為了填滿篇幅補出不必要設定。

## Puzzle Generation 設定

- `reviewer_enabled`：是否啟用能看見完整內容的 reviewer agent。
- `deterministic_gate_enabled`：是否啟用程式化品質檢查。
- `max_revision_rounds`：reviewer 或 deterministic gate 不通過時，最多修正輪數。
- `strict_surface_story_max_chars`：生成 pipeline 使用的謎面嚴格字數上限。
- `strict_truth_min_chars`：生成 pipeline 使用的真相嚴格字數下限。
- `strict_truth_max_chars`：生成 pipeline 使用的真相嚴格字數上限。

詳細流程見 `docs/design/puzzle-generation-pipeline.md`。

## Storage 設定

- `data_dir`：資料根目錄。
- `games_dir`：已結束遊戲 JSON 儲存目錄。

## API 設定

- `cors_origins`：允許前端開發伺服器來源。

## Logging 設定

- `level`：後端 log level，可由 `.env` 的 `LOG_LEVEL` 覆蓋。
- `format`：第一版固定建議使用 `json`。
- `log_dir`：本地 log 目錄。
- `file_enabled`：是否輸出到 rotating file。
- `console_enabled`：是否輸出到 console。
- `max_file_mb`：單一 log 檔最大大小。
- `backup_count`：rotation 備份數。
- `log_prompt_preview`：是否記錄 prompt preview，預設關閉。
- `prompt_preview_chars`：prompt preview 最大字數。
- `log_llm_output_preview`：是否記錄 LLM output preview，預設關閉。
- `llm_output_preview_chars`：LLM output preview 最大字數。
- `raw_message_mode`：raw message log 模式，`off | preview | full`，本機開發預設 `full`。
- `raw_message_log_file`：raw message log 輸出檔案，預設 `logs/messages.log`。
- `raw_message_max_chars`：raw message 單筆最大字數，超過時截斷。
- `raw_message_include_player_messages`：是否記錄玩家 topic/question/solution。
- `raw_message_include_llm_prompts`：是否記錄送給 LLM 的 system/human prompt。
- `raw_message_include_llm_responses`：是否記錄 LLM provider raw response。
- `raw_message_include_parsed_outputs`：是否記錄 parsed structured output。

`raw_message_mode = "full"` 會保存完整謎底、key facts、prompt 與模型輸出。此專案以本機開發觀測為主，因此這是可接受的預設；log 檔仍不得 commit。

詳細設計見 `docs/design/logging-design.md`。
