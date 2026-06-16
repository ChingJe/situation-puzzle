# Situation Puzzle

單人海龜湯遊戲專案。玩家輸入主題後，由 Ollama 模型生成謎面與隱藏真相；玩家透過是非題提問，最後提交解答。

## 需求

- Python 3.12+
- uv
- Node.js 18.19+（目前使用 Vite 6，以相容本機 Node 18）
- npm
- Ollama
- Ollama 模型：`gemma4:12b`

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
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma4:12b
```

`config.toml` 負責應用行為參數，例如 LLM retry、謎面字數、JSON 儲存路徑與 CORS。

## Ollama

確認 Ollama 已啟動，並準備模型：

```bash
ollama pull gemma4:12b
```

後端 health check 會檢查 Ollama 與模型是否可用。Ollama 不可用時 API 仍會啟動，但 `/api/health` 會回傳 `degraded`。

## 開發命令

後端：

```bash
uv run fastapi dev backend/app/main.py
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

預設前端開發伺服器為 <http://localhost:5173>，後端為 <http://localhost:8000>。Vite 已設定 `/api` proxy 到後端。

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

## API 摘要

- `GET /api/health`
- `POST /api/games`
- `GET /api/games/{game_id}`
- `POST /api/games/{game_id}/questions`
- `POST /api/games/{game_id}/solution`
- `POST /api/games/{game_id}/abandon`
- `GET /api/history`
- `GET /api/history/{game_id}`

完整設計見 `docs/`。
