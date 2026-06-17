# Situation Puzzle

單人海龜湯遊戲專案。玩家輸入任意中文主題後，後端透過本機 LLM runtime 生成謎面、真相與解答判定資料；玩家只能以是非題提問，AI 主持人只回答「是／否／無關」，最後由玩家提交解答並由 AI 判定是否解開。

目前預設使用 llama.cpp OpenAI-compatible API 搭配 `qwen3.6-35b-a3b`，Ollama 仍保留為替代 provider。

## 文件入口

- [docs/README.md](docs/README.md)：文件總覽。
- [docs/design/README.md](docs/design/README.md)：目前有效的系統架構與設計收斂入口。
- [docs/plans/](docs/plans/)：開發計畫與 prompt 測試計畫。
- [docs/issue/](docs/issue/)：實測後整理出的問題紀錄。
- [docs/prompt-tests/README.md](docs/prompt-tests/README.md)：prompt 測試資料整理。
- [docs/workflow_log.md](docs/workflow_log.md)：本專案與 agent 協作開發的完整對話與實作紀錄。

若文件內容彼此衝突，優先以 [docs/design/README.md](docs/design/README.md) 的收斂說明為準。

## 專案結構

```text
backend/           FastAPI 後端、LangGraph 流程、資料模型與測試
frontend/          React + Vite + TypeScript 前端
docs/              設計、計畫、問題紀錄、prompt 測試與 workflow log
data/games/        已結束遊戲的本地 JSON 儲存位置，不進 git
logs/              本地 structured log 與 raw message log，不進 git
tools/             prompt lab 與測試輔助工具
config.toml        應用行為設定
.env.example       本機環境變數範例
Makefile           常用開發命令
```

## 前置需求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Node.js 18.19+
- npm
- Git
- llama.cpp OpenAI-compatible server，預設 port 為 `18080`

可選：

- Ollama，預設 port 為 `11434`
- `gemma4:e4b`，作為 Ollama fallback 或較輕量測試用模型

## 本地初始化

1. 安裝 Python 依賴：

```bash
uv sync
```

2. 安裝前端依賴：

```bash
cd frontend
npm install
cd ..
```

3. 建立本機環境變數：

```bash
cp .env.example .env
```

4. 依照本機 LLM runtime 調整 `.env`。

llama.cpp 在同一台環境中執行時：

```env
LLM_PROVIDER=openai-compatible
OPENAI_COMPATIBLE_BASE_URL=http://localhost:18080/v1
OPENAI_COMPATIBLE_MODEL=qwen3.6-35b-a3b
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma4:e4b
LOG_LEVEL=INFO
```

若後端跑在 WSL，而 llama.cpp 跑在 Windows 端，`OPENAI_COMPATIBLE_BASE_URL` 通常需要改成 Windows gateway IP：

```bash
ip route | grep default | awk '{print $3}'
```

例如：

```env
OPENAI_COMPATIBLE_BASE_URL=http://172.x.x.x:18080/v1
```

5. 確認 llama.cpp server 可連線：

```bash
curl http://localhost:18080/v1/models
```

如果使用 WSL gateway IP，請把 `localhost` 換成對應 IP。

## 設定分工

`.env` 放每台機器不同的環境值，例如：

- `LLM_PROVIDER`
- `OPENAI_COMPATIBLE_BASE_URL`
- `OPENAI_COMPATIBLE_MODEL`
- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `LOG_LEVEL`

[config.toml](config.toml) 放應用行為設定，例如：

- LLM retry 次數
- 題目生成限制
- JSON 儲存路徑
- CORS 設定
- logging 與 raw message log 行為

詳細設計見 [docs/design/config.md](docs/design/config.md)。

## 啟動開發環境

後端：

```bash
make dev-backend
```

等同於：

```bash
uv run fastapi dev backend/app/main.py --host 0.0.0.0 --reload-dir backend
```

前端：

```bash
make dev-frontend
```

等同於：

```bash
cd frontend
npm run dev
```

預設網址：

- 前端：<http://localhost:5173>
- 後端：<http://localhost:8000>
- 後端 health check：<http://localhost:8000/api/health>

Vite 已設定 `/api` proxy 到後端。後端 reload watcher 只監看 `backend/`，避免 `logs/` 或 `data/` 寫入造成 dev server 反覆 reload。

WSL 中若 Windows 瀏覽器無法透過 `localhost:5173` 連入，可查詢 WSL IP 後改用該 IP：

```bash
hostname -I
```

例如：

```text
http://172.x.x.x:5173/
```

## 測試與檢查

後端測試：

```bash
make test-backend
```

等同於：

```bash
uv run pytest
```

前端編譯檢查：

```bash
make check-frontend
```

等同於：

```bash
cd frontend
npm run build
```

## 操作流程

1. 啟動 llama.cpp OpenAI-compatible server。
2. 啟動後端：`make dev-backend`。
3. 啟動前端：`make dev-frontend`。
4. 開啟 <http://localhost:5173>。
5. 在前端輸入中文主題建立一局遊戲。
6. 透過是非題提問。
7. 用提交解答按鈕送出最終答案。
8. 遊戲結束後，可在歷史紀錄頁查看已保存結果。

進行中遊戲只存在後端記憶體中；後端重啟後，進行中的局會失效。已結束或放棄的遊戲會保存到 `data/games/{game_id}.json`。

## Logging

後端使用 JSON lines structured logging，預設輸出到 console 與：

```text
logs/app.log
```

raw prompt、user request、agent/LLM 回覆與解析結果會寫入 raw message log：

```text
logs/messages.log
```

每個 HTTP request 會帶 `request_id`，建立遊戲後相關事件也會帶 `game_id`。常用查詢方式：

```bash
rg '"request_id":"req_..."' logs/app.log logs/messages.log
rg '"game_id":"..."' logs/app.log logs/messages.log
```

log 與 raw message 的設計取捨見 [docs/design/logging-design.md](docs/design/logging-design.md)。

## API 摘要

- `GET /api/health`
- `POST /api/games`
- `GET /api/games/{game_id}`
- `POST /api/games/{game_id}/questions`
- `POST /api/games/{game_id}/solution`
- `POST /api/games/{game_id}/abandon`
- `GET /api/history`
- `GET /api/history/{game_id}`

完整 API contract 見 [docs/design/api-design.md](docs/design/api-design.md)。

## 目前設計重點

題目生成已收斂為多節點 pipeline：

```text
interpret_topic
  -> generate_core_truth
  -> expand_truth
  -> extract_solution_facts
  -> write_surface_story
  -> generate_assumptions
  -> review_puzzle
  -> finalize_puzzle
```

核心設計文件：

- [docs/design/architecture.md](docs/design/architecture.md)：整體系統分層。
- [docs/design/puzzle-generation-pipeline.md](docs/design/puzzle-generation-pipeline.md)：題目生成 pipeline。
- [docs/design/prompt-contract.md](docs/design/prompt-contract.md)：各 agent prompt 的責任與邊界。
- [docs/design/puzzle-quality-contract.md](docs/design/puzzle-quality-contract.md)：題目品質與資料 contract。
- [docs/design/game-flow.md](docs/design/game-flow.md)：遊戲流程與狀態轉換。
- [docs/design/frontend-design.md](docs/design/frontend-design.md)：前端互動設計。
- [docs/design/data-model.md](docs/design/data-model.md)：資料模型與保存格式。

## Git

本專案使用 git 進行版本控制。一般開發流程：

```bash
git status --short
git add <files>
git commit -m "<message>"
git push
```

`data/games/*.json`、`logs/*.log`、前端 build output 與本地環境檔不應提交。
