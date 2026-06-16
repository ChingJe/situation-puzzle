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
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma4:12b
```

欄位：

- `OLLAMA_BASE_URL`：Ollama API base URL。
- `OLLAMA_MODEL`：預設模型名稱。

## `config.toml`

```toml
[llm]
request_timeout_seconds = 120
request_max_retries = 2
structured_output_max_retries = 2
generation_temperature = 0.8
answer_temperature = 0.1
judge_temperature = 0.1

[puzzle]
surface_story_max_chars = 150
truth_min_chars = 300
truth_max_chars = 800
key_facts_min = 4
key_facts_max = 8
language = "zh-TW"
content_style = "懸疑、適合一般玩家、避免露骨血腥描寫"

[storage]
data_dir = "data"
games_dir = "data/games"

[api]
cors_origins = ["http://localhost:5173"]
```

## LLM 設定

- `request_timeout_seconds`：每次 Ollama request timeout。
- `request_max_retries`：連線、timeout、5xx 等 request retry 次數。
- `structured_output_max_retries`：模型輸出不符合 schema 時的 retry 次數。
- `generation_temperature`：題目生成溫度，預設 `0.8`。
- `answer_temperature`：是非題判定溫度，預設 `0.1`。
- `judge_temperature`：解答判定溫度，預設 `0.1`。

## Puzzle 設定

- `surface_story_max_chars`：謎面最大字數。
- `truth_min_chars`：真相最少字數。
- `truth_max_chars`：真相最多字數。
- `key_facts_min`：關鍵事實最少條數。
- `key_facts_max`：關鍵事實最多條數。
- `language`：生成語言，第一版固定 `zh-TW`。
- `content_style`：題材與內容風格限制。

## Storage 設定

- `data_dir`：資料根目錄。
- `games_dir`：已結束遊戲 JSON 儲存目錄。

## API 設定

- `cors_origins`：允許前端開發伺服器來源。

