# Situation Puzzle

單人海龜湯遊戲專案。玩家輸入主題後，由本機 LLM runtime 生成謎面與隱藏真相；玩家透過是非題提問，最後提交解答。

## 需求

- Python 3.12+
- uv
- Node.js 18.19+（目前使用 Vite 6，以相容本機 Node 18）
- npm
- llama.cpp OpenAI-compatible server
- 預設生成模型：`qwen3.6-35b-a3b`
- Ollama 與 `gemma4:e4b` 可作為輕量測試或 fallback runtime

## 初始化

Python 環境：

```bash
uv sync
```

前端依賴：

```bash
cd frontend
npm install
```

建立本機環境變數：

```bash
cp .env.example .env
```

`.env` 負責不同機器會變的值：

```env
LLM_PROVIDER=openai-compatible
OPENAI_COMPATIBLE_BASE_URL=http://localhost:18080/v1
OPENAI_COMPATIBLE_MODEL=qwen3.6-35b-a3b
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma4:e4b
```

`config.toml` 負責應用行為參數，例如 LLM retry、謎面字數、JSON 儲存路徑與 CORS。

## LLM Runtime

預設方向是使用 llama.cpp 的 OpenAI-compatible API 搭配 `qwen3.6-35b-a3b`。若 runtime 在 Windows 端、後端在 WSL，`OPENAI_COMPATIBLE_BASE_URL` 通常需要使用 Windows gateway IP，例如：

```env
LLM_PROVIDER=openai-compatible
OPENAI_COMPATIBLE_BASE_URL=http://192.168.192.1:18080/v1
OPENAI_COMPATIBLE_MODEL=qwen3.6-35b-a3b
```

可用下列 endpoint 檢查 llama.cpp server 是否可連線：

```bash
curl http://192.168.192.1:18080/v1/models
```

Ollama 仍可作為替代 runtime。若使用 Ollama，確認 Ollama 已啟動並準備模型：

```bash
ollama pull gemma4:e4b
```

後端 health check 會檢查目前選定的 LLM provider 與模型是否可用。LLM runtime 不可用時 API 仍會啟動，但 `/api/health` 會回傳 `degraded`。

正式後端已支援 `LLM_PROVIDER=openai-compatible` 與 `LLM_PROVIDER=ollama` 切換。預設建議使用 llama.cpp + Qwen；Ollama 可保留作為替代 runtime。

## 開發命令

後端：

```bash
uv run fastapi dev backend/app/main.py --host 0.0.0.0 --reload-dir backend
```

前端：

```bash
cd frontend
npm run dev
```

也可以使用 Makefile：

```bash
make dev-backend
make dev-frontend
```

預設前端開發伺服器為 <http://localhost:5173>，後端為 <http://localhost:8000>。Vite 已設定 `/api` proxy 到後端。後端 reload watcher 只監看 `backend/`，避免 `logs/` 或 `data/` 寫入造成 dev server 反覆偵測變更。

WSL 環境中，dev server 會監聽 `0.0.0.0`，若 Windows 瀏覽器無法使用 `localhost` 連入，可在 WSL 查詢 IP 後改用該 IP：

```bash
hostname -I
```

例如：

```text
http://172.x.x.x:5173/
```

## 測試與檢查

後端：

```bash
uv run pytest
```

前端：

```bash
cd frontend
npm run build
```

Makefile：

```bash
make test-backend
make check-frontend
```

## 資料儲存

進行中遊戲只存在後端記憶體中。後端重啟後，進行中遊戲會失效。

已解開或放棄的遊戲會保存到：

```text
data/games/{game_id}.json
```

`data/games/*.json` 不進 git。

## Logging

後端使用 JSON lines structured logging。預設同時輸出到 console 與：

```text
logs/app.log
```

每個 HTTP request 會有 `X-Request-ID`，後端 log 也會帶 `request_id`。建立遊戲後，相關事件會帶 `game_id`，可用 `rg` 或 `jq` 查詢：

```bash
rg '"request_id":"req_..."' logs/app.log
rg '"game_id":"..."' logs/app.log
```

本機 log level 可在 `.env` 調整：

```env
LOG_LEVEL=INFO
```

Structured event log 預設只保留摘要；完整 prompt、模型回覆與解析結果由 raw message log 管理。詳細設計見 `docs/design/logging-design.md`。

## API 摘要

- `GET /api/health`
- `POST /api/games`
- `GET /api/games/{game_id}`
- `POST /api/games/{game_id}/questions`
- `POST /api/games/{game_id}/solution`
- `POST /api/games/{game_id}/abandon`
- `GET /api/history`
- `GET /api/history/{game_id}`

完整設計見 `docs/design/`，開發與測試計畫見 `docs/plans/`，已知問題紀錄見 `docs/issue/`。
