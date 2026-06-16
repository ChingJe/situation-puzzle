# 整體架構設計

## 目標

本專案是一個單人海龜湯遊戲。玩家輸入任意主題後，由 AI 生成一局完整題目；玩家只能透過是非題向 AI 主持人提問，最後按下提交解答，由 AI 判定是否解開真相。

## 技術棧

- Python：後端主體
- uv：Python 環境與依賴管理
- FastAPI：REST API
- LangGraph：遊戲流程與狀態轉移
- LangChain + ChatOllama：Ollama API 呼叫與 structured output
- Ollama：本地 LLM runtime
- 預設模型：`gemma4:e4b`
- React + Vite + TypeScript：前端互動介面
- JSON 檔案：結束後遊戲紀錄儲存
- Git：版本控制

## 系統邊界

第一版只支援：

- 單人玩家對 AI 主持人
- 使用者輸入主題，AI 生成題目
- 遊戲中主持人只回答「是」「否」「無關」
- 玩家按鈕提交解答
- 可無限提問，沒有失敗條件
- 可放棄並查看答案
- 結束後保存該局 JSON 紀錄
- 前端刷新後可恢復仍存在後端記憶體中的進行中遊戲

第一版不支援：

- 多人遊戲
- WebSocket 或串流輸出
- SQLite 或外部資料庫
- 後端重啟後恢復進行中遊戲
- 難度選項
- 前端端到端測試

## 建議目錄結構

```text
situation-puzzle/
  backend/
    app/
      main.py
      config.py
      errors.py
      models.py
      storage.py
      llm/
        __init__.py
        client.py
        prompts.py
      graph/
        __init__.py
        state.py
        workflow.py
        nodes.py
      services/
        __init__.py
        game_service.py
    tests/
  frontend/
    src/
      api/
      components/
      pages/
      types/
    package.json
  data/
    games/
  docs/
  config.toml
  pyproject.toml
  uv.lock
  Makefile
  README.md
  .env.example
  .gitignore
```

## 後端模組責任

- `main.py`：FastAPI app、router 掛載、CORS、health check。
- `config.py`：載入 `config.toml`、`.env` 與環境變數，建立 Settings。
- `errors.py`：統一 API 錯誤格式與錯誤碼。
- `models.py`：API request/response、遊戲紀錄、structured output schema。
- `storage.py`：讀寫 `data/games/*.json`、歷史紀錄摘要。
- `llm/client.py`：建立 ChatOllama、structured output、retry 封裝。
- `llm/prompts.py`：題目生成、問題判定、解答判定 prompts。
- `graph/state.py`：LangGraph 狀態定義。
- `graph/nodes.py`：`generate_puzzle`、`answer_question`、`judge_solution`、`finalize_game`。
- `graph/workflow.py`：LangGraph workflow 建立與編譯。
- `services/game_service.py`：遊戲生命週期、記憶體 session 管理、呼叫 graph、呼叫 storage。

## 前端模組責任

- `api/`：REST API client 與錯誤處理。
- `types/`：前後端共享概念的 TypeScript 型別。
- `components/`：Tab、謎面、問答紀錄、歷史紀錄、表單元件。
- `pages/`：目前遊戲與歷史紀錄兩個主要視圖。

## 資料流

1. 玩家輸入主題。
2. 前端呼叫 `POST /api/games`。
3. 後端透過 LangGraph `generate_puzzle` 節點呼叫 Ollama。
4. AI 回傳結構化題目，後端只把謎面回傳給前端。
5. 玩家提問，前端呼叫 `POST /api/games/{game_id}/questions`。
6. 後端驗證問題是否為可回答的是非題，並回傳「是」「否」「無關」。
7. 玩家提交解答，前端呼叫 `POST /api/games/{game_id}/solution`。
8. AI 判定是否解開。未解開時只回「尚未解開」。
9. 解開或放棄後，後端寫入 `data/games/{game_id}.json`。
10. 歷史紀錄頁讀取已結束遊戲 JSON 並以對話紀錄形式渲染。
