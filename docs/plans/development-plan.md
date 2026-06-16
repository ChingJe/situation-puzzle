# 開發計畫

## 目的

本文件將既有設計拆成可執行的開發階段，作為後續實作、測試與驗收的依據。每個階段都應維持可執行、可測試，避免跨太多模組一次完成。

## 開發原則

- 先完成後端核心資料模型與狀態轉移，再接上真實 LLM。
- LLM 相關測試以 fake/stub 為主，不依賴本機 Ollama。
- API response 不得在進行中遊戲洩漏 `truth`、`key_facts`、`forbidden_assumptions`。
- 每個階段完成後至少執行 `uv run pytest`；牽涉前端時執行 `npm run build`。
- JSON 儲存只保存已結束遊戲，進行中遊戲存在後端記憶體。
- 前端先完成可用流程，再補視覺細節。

## 階段 0：專案基礎與工具鏈

目前狀態：已完成。

涵蓋內容：

- uv venv 與 Python 依賴設定。
- FastAPI 基礎 app。
- React + Vite + TypeScript 基礎 app。
- `config.toml`、`.env.example`、`.gitignore`、`Makefile`。
- 最小 health check 與測試。

驗收標準：

- `uv run pytest` 通過。
- `npm run build` 通過。
- `npm audit` 無已知漏洞。
- `GET /api/health` 回傳後端狀態。

後續注意：

- 目前 Node 18 無法使用 Vite 8。若升級到 Node 20.19+，可重新評估 Vite 與圖示庫版本。

## 階段 1：後端資料模型與錯誤格式

目標：

建立所有後端模組共用的資料契約，先不接 LLM。

主要檔案：

- `backend/app/models.py`
- `backend/app/errors.py`
- `backend/tests/test_models.py`
- `backend/tests/test_errors.py`

實作內容：

- 定義 enum：
  - `GameStatus`: `playing | solved | abandoned`
  - `Answer`: `yes | no | irrelevant`
  - `Difficulty`: `easy | medium | hard`
- 定義 structured output schema：
  - `PuzzleDraft`
  - `QuestionJudgement`
  - `SolutionJudgement`
- 定義遊戲紀錄 schema：
  - `Puzzle`
  - `QuestionRecord`
  - `SolutionAttempt`
  - `GameSession`
  - `CompletedGameRecord`
  - `HistoryItem`
- 定義 API request/response schema。
- 定義 `ApiErrorCode` 與統一錯誤 response helper。

模組交界：

- API layer 只回傳 response schema，不直接暴露內部 record。
- Service layer 使用 `GameSession` 管理記憶體狀態。
- Storage layer 使用 `CompletedGameRecord` 寫入 JSON。
- LLM layer 使用 structured output schema。

驗收標準：

- Pydantic 驗證可阻擋不合法 enum、缺欄位、錯誤型別。
- `display_answer` 可從 `Answer` 穩定轉成中文。
- 進行中遊戲可見 response 不包含隱藏欄位。
- `uv run pytest` 通過。

## 階段 2：設定與 Health Check 完整化

目標：

讓後端正確載入 `.env`、環境變數與 `config.toml`，並完整檢查 Ollama 與 storage 狀態。

主要檔案：

- `backend/app/config.py`
- `backend/app/health.py` 或 `backend/app/main.py`
- `backend/app/llm/client.py`
- `backend/app/storage.py`
- `backend/tests/test_config.py`
- `backend/tests/test_health.py`

實作內容：

- 確認設定載入順序：
  1. `config.toml`
  2. `.env`
  3. 系統環境變數覆蓋
- 實作 storage writable check。
- 實作 Ollama health check：
  - base URL 是否可連線。
  - configured model 是否存在。
- `GET /api/health` 回傳 `ok` 或 `degraded`。

模組交界：

- `config.py` 不依賴 FastAPI。
- health check 可呼叫 storage/llm 的輕量檢查方法，但不得觸發題目生成。
- Ollama 不可用時，後端仍可啟動。

驗收標準：

- 沒有 Ollama 時，health 回傳 `degraded`，API 仍可啟動。
- storage 目錄不存在時可建立，或回報明確錯誤。
- 環境變數可覆蓋 `.env`。
- `uv run pytest` 通過。

## 階段 3：Storage Layer

目標：

完成已結束遊戲 JSON 持久化與歷史紀錄查詢。

主要檔案：

- `backend/app/storage.py`
- `backend/tests/test_storage.py`

實作內容：

- 建立 `data/games/`。
- 寫入 `CompletedGameRecord` 到 `data/games/{game_id}.json`。
- 讀取單一歷史紀錄。
- 掃描歷史列表並輸出 `HistoryItem`。
- 歷史列表依 `ended_at` 由新到舊排序。
- 處理 JSON 檔案損壞、缺欄位、讀寫失敗。

模組交界：

- Storage layer 不知道 FastAPI request。
- Storage layer 不呼叫 LLM。
- Game service 在 `solved` 或 `abandoned` 時呼叫 storage。

驗收標準：

- 使用 pytest temporary directory，不污染真實 `data/games`。
- solved/abandoned 皆可寫入。
- `data/games/*.json` 不進 git。
- 損壞 JSON 不應讓整個歷史列表 API 崩潰。
- `uv run pytest` 通過。

## 階段 4：LLM Client、Prompts 與 Fake LLM

目標：

建立真實 Ollama client 與測試用 fake client 的一致介面，並封裝 structured output retry。題目生成應支援多節點 pipeline，而不是只提供單一 `generate_puzzle` 呼叫。

主要檔案：

- `backend/app/llm/client.py`
- `backend/app/llm/prompts.py`
- `backend/tests/test_llm_client.py`

實作內容：

- 使用 `ChatOllama.with_structured_output(...)`。
- 分別建立遊戲所需任務：
  - `interpret_topic`
  - `generate_core_truth`
  - `expand_truth`
  - `extract_key_facts`
  - `write_surface_story`
  - `generate_forbidden_assumptions`
  - `review_puzzle`
  - `answer_question`
  - `judge_solution`
- 封裝 request retry 與 structured output retry。
- prompts 固定要求繁體中文與指定內容限制。
- prompts 禁止問答階段輸出額外說明。
- 建立 fake/stub LLM 供 service 與 graph 測試使用。

模組交界：

- LLM client 回傳 Pydantic schema，不回傳 raw JSON 字串。
- Graph node 不處理 JSON 修復細節。
- Service 測試預設注入 fake LLM。

驗收標準：

- structured output 第一次失敗、第二次成功時可通過。
- retry 用盡時轉成 `LLM_OUTPUT_INVALID`。
- 連線錯誤轉成 `LLM_UNAVAILABLE`。
- 題目生成各 draft schema 包含必要欄位，並可組成正式 `Puzzle`。
- `uv run pytest` 通過。

## 階段 5：LangGraph Workflow

目標：

把 LLM 任務包成清楚的 graph workflow，讓遊戲流程可測、可替換。

主要檔案：

- `backend/app/graph/state.py`
- `backend/app/graph/nodes.py`
- `backend/app/graph/workflow.py`
- `backend/tests/test_graph.py`

實作內容：

- 定義 graph state。
- 實作節點：
  - `generate_puzzle_pipeline`
  - `interpret_topic`
  - `generate_core_truth`
  - `expand_truth`
  - `extract_key_facts`
  - `write_surface_story`
  - `generate_forbidden_assumptions`
  - `review_puzzle`
  - `finalize_puzzle`
  - `answer_question`
  - `judge_solution`
  - `finalize_game`
- 建立 workflow factory，允許注入 fake LLM 與 storage。
- 將 yes/no/irrelevant 判定限制在 schema 與 prompt 中。

模組交界：

- Graph 不直接讀寫 FastAPI response。
- Graph 可回傳 domain result，由 service 決定 API response。
- `finalize_game` 可先保持輕量，實際寫入可由 service 統一控制，以避免 graph 與 storage 耦合過深。

驗收標準：

- fake LLM 可驅動完整建立題目、提問、判定解答流程。
- reviewer 不通過時可依 `target_node` 回到最小必要節點修正。
- revision 次數超過設定時回 `LLM_OUTPUT_INVALID`。
- 無效問題不產生正式 `QuestionRecord`。
- 未解開只回傳 solved=false，不包含提示資訊。
- `uv run pytest` 通過。

## 階段 6：Game Service

目標：

建立後端遊戲生命週期中心，管理進行中 session、狀態轉移與完成後保存。

主要檔案：

- `backend/app/services/game_service.py`
- `backend/tests/test_game_service.py`

實作內容：

- `create_game(topic)`
- `get_game(game_id)`
- `ask_question(game_id, question)`
- `submit_solution(game_id, solution)`
- `abandon_game(game_id)`
- 管理多局進行中遊戲。
- 遊戲結束後呼叫 storage 寫入 JSON。
- 已結束遊戲不可再提問或提交解答。

模組交界：

- API router 只呼叫 service。
- Service 負責把 domain exception 轉成可被 API handler 處理的錯誤。
- Service 保證進行中 response 不包含隱藏答案。

驗收標準：

- 可同時建立多局。
- `GET /api/games/{game_id}` 可恢復記憶體中的進行中遊戲。
- 解開時 status 轉 `solved` 並保存。
- 放棄時 status 轉 `abandoned` 並保存。
- 已結束操作回 `GAME_ALREADY_ENDED`。
- `uv run pytest` 通過。

## 階段 7：REST API Router

目標：

完成所有前端需要的 REST endpoints。

主要檔案：

- `backend/app/main.py`
- `backend/app/routes/games.py`
- `backend/app/routes/history.py`
- `backend/app/errors.py`
- `backend/tests/test_api_games.py`
- `backend/tests/test_api_history.py`

實作內容：

- `POST /api/games`
- `GET /api/games/{game_id}`
- `POST /api/games/{game_id}/questions`
- `POST /api/games/{game_id}/solution`
- `POST /api/games/{game_id}/abandon`
- `GET /api/history`
- `GET /api/history/{game_id}`
- 統一 exception handler。

模組交界：

- Router 不直接呼叫 LLM。
- Router 不直接讀寫 JSON。
- Router 不組裝 domain 邏輯，只轉 request/response。

驗收標準：

- 所有 API response 符合 `docs/design/api-design.md`。
- 錯誤 response 一律符合統一格式。
- 遊戲進行中 API 不洩漏 `truth` 等隱藏欄位。
- API 測試使用 fake LLM，不依賴 Ollama。
- `uv run pytest` 通過。

## 階段 8：前端 API Client 與狀態模型

目標：

在前端建立 typed API client 與 UI 狀態模型，先不追求完整視覺。

主要檔案：

- `frontend/src/api/client.ts`
- `frontend/src/types/api.ts`
- `frontend/src/types/game.ts`
- `frontend/src/state/useGameState.ts` 或同等模組

實作內容：

- 封裝 API calls。
- 定義 TypeScript 型別：
  - current game
  - question record
  - solution attempt
  - history item/detail
  - API error
- 處理統一錯誤格式。
- 保存與恢復 `current_game_id`。
- 建立 loading/error 狀態。

模組交界：

- UI component 不直接寫 fetch。
- API client 不處理畫面文字，只回傳資料或 typed error。
- 狀態層負責 localStorage。

驗收標準：

- `npm run build` 通過。
- API client 可處理成功與錯誤 response。
- 刷新恢復失敗時會清除 `current_game_id`。

## 階段 9：目前遊戲 UI

目標：

完成主要遊戲互動：建立遊戲、提問、提交解答、放棄。

主要檔案：

- `frontend/src/pages/CurrentGamePage.tsx`
- `frontend/src/components/NewGameForm.tsx`
- `frontend/src/components/PuzzlePanel.tsx`
- `frontend/src/components/QuestionForm.tsx`
- `frontend/src/components/QuestionLog.tsx`
- `frontend/src/components/SolutionForm.tsx`

實作內容：

- 主題輸入與建立遊戲。
- 若已有進行中遊戲，建立新局前跳確認。
- 顯示謎面。
- 提問送出後清空輸入並禁用按鈕。
- 無效問題顯示錯誤，不加入紀錄。
- 提交解答未成功時顯示「尚未解開」。
- 成功或放棄後顯示真相並禁用遊戲操作。

模組交界：

- UI 只使用 API client/state hook。
- 顯示文字以繁體中文為主。
- 目前遊戲頁不讀取歷史 JSON detail，除非切到歷史頁。

驗收標準：

- `npm run build` 通過。
- 所有指定 UI 狀態都有明確呈現。
- 長文字在桌面與手機寬度不重疊。

## 階段 10：歷史紀錄 UI

目標：

完成已結束遊戲列表與詳情檢視。

主要檔案：

- `frontend/src/pages/HistoryPage.tsx`
- `frontend/src/components/HistoryList.tsx`
- `frontend/src/components/HistoryDetail.tsx`
- `frontend/src/components/ConversationTranscript.tsx`

實作內容：

- 呼叫 `GET /api/history`。
- 點選一筆歷史紀錄後呼叫 `GET /api/history/{game_id}`。
- 顯示謎面、結束狀態、問答紀錄、解答嘗試、完整真相。
- 問答以對話形式呈現。

模組交界：

- 歷史頁只讀已結束遊戲。
- 歷史 detail 可以顯示 `truth`。
- 歷史頁不操作進行中遊戲狀態。

驗收標準：

- 無歷史紀錄時有空狀態。
- 損壞或讀取失敗時顯示 API 錯誤。
- `npm run build` 通過。

## 階段 11：整合 Ollama 與人工驗收

目標：

用真實 `gemma4:e4b` 跑完整遊戲流程，調整 prompts 與 retry 設定。

前置條件：

- 本機 Ollama 已啟動。
- 已安裝 `gemma4:e4b`。
- `.env` 設定正確。

驗收流程：

1. 開啟後端與前端。
2. 檢查 `/api/health` 顯示 Ollama available。
3. 用中文主題建立新遊戲。
4. 確認謎面不超過設定字數，且未暴露真相。
5. 提問有效是非題，確認只回「是」「否」「無關」。
6. 輸入非是非題，確認顯示固定錯誤。
7. 提交錯誤解答，確認只顯示「尚未解開」。
8. 提交正確解答或放棄，確認顯示真相。
9. 確認 `data/games/{game_id}.json` 寫入。
10. 確認歷史頁可讀取該局。

調整重點：

- 若題目太直白，調整 generation prompt。
- 若問答常誤判，補強 `forbidden_assumptions` 與 answer prompt。
- 若解答判定過寬或過嚴，調整 judge prompt。
- 若 structured output 不穩，調整 schema 描述與 retry 次數。

驗收標準：

- 至少完成 3 局不同主題人工測試。
- 每局都能建立、提問、提交或放棄、保存、讀歷史。
- `uv run pytest` 通過。
- `npm run build` 通過。

## 階段 12：文件與開發體驗整理

目標：

讓專案能被穩定啟動、測試與交接。

主要檔案：

- `README.md`
- `docs/*.md`
- `docs/design/*.md`
- `docs/issue/*.md`
- `Makefile`

實作內容：

- 補 README：
  - Python/Node 版本需求。
  - Ollama 安裝與模型準備。
  - `.env` 設定。
  - 後端/前端啟動方式。
  - 測試命令。
- 更新設計文件與實作差異。
- 檢查 Makefile 命令。

驗收標準：

- 新環境照 README 可完成初始化。
- `make test-backend` 通過。
- `make check-frontend` 通過。

## 階段 13：Logging 與可觀察性

目標：

補上後端 structured logging，讓開發者可以觀察 API request、GameService 狀態轉移、LangGraph 節點、LLM call/retry/failure、storage 與環境 health。

主要檔案：

- `backend/app/logging_config.py`
- `backend/app/middleware.py`
- `backend/app/services/game_service.py`
- `backend/app/graph/workflow.py`
- `backend/app/graph/nodes.py`
- `backend/app/llm/client.py`
- `backend/app/storage.py`
- `backend/app/health.py`
- `backend/tests/test_logging.py`
- `docs/design/logging-design.md`

實作內容：

- 新增 `config.toml` `[logging]` 設定。
- 新增 `.env` 的 `LOG_LEVEL` 覆蓋。
- 實作 JSON lines formatter。
- 實作 rotating file handler，預設輸出 `logs/app.log`。
- 實作 raw message handler，本機開發預設 full，輸出 `logs/messages.log`。
- 實作 request id middleware，response 回傳 `X-Request-ID`。
- 使用 contextvars 讓同一 request 內 log 自動帶 `request_id`。
- GameService 記錄 create、ask、invalid question、submit、abandon、finalize。
- Graph workflow/node 記錄 node start/end/failure。
- LLM client 記錄 task、model、retry、structured output validation failure、duration。
- LLM client 可選擇記錄完整 system prompt、human prompt、Ollama raw response、parsed output。
- GameService 可選擇記錄玩家 topic、question、solution raw message。
- Storage 記錄 read/write/list 與 corrupt JSON skipped。
- Health 記錄 Ollama/storage summary。
- structured event log 保持摘要化；完整 `truth`、`key_facts`、`forbidden_assumptions` 由 raw message log 保存。

驗收標準：

- `POST /api/games` 可在 log 中用同一個 `request_id` 串起 route、service、graph、LLM 事件。
- 同一局可用 `game_id` 查到所有 game lifecycle 事件。
- Ollama unavailable、model not found、structured output failure 均有明確 log。
- 無效問題記錄 `INVALID_QUESTION`，但不寫入正式問答紀錄。
- storage 損壞 JSON 被跳過時有 warning log。
- raw message 預設 full，可用 `request_id` 與 `llm_call_id` 查完整玩家輸入、agent prompt、Ollama response、parsed output。
- pytest 可驗證 structured event log 仍維持摘要化，raw message log 則保留完整內容。
- `uv run pytest` 通過。

## 階段 14：題目生成 Pipeline 重構

目標：

將目前一次完成的題目生成重構成多節點 LangGraph pipeline，加入 reviewer agent 與 deterministic gate，解決謎面、真相、關鍵事實不一致，以及短主題過度發散的問題。

主要檔案：

- `backend/app/models.py`
- `backend/app/config.py`
- `backend/app/llm/client.py`
- `backend/app/llm/prompts.py`
- `backend/app/graph/state.py`
- `backend/app/graph/nodes.py`
- `backend/app/graph/workflow.py`
- `backend/tests/test_puzzle_generation_pipeline.py`
- `backend/tests/test_prompts.py`
- `docs/design/puzzle-generation-pipeline.md`

實作內容：

- 新增 draft schema：
  - `TopicInterpretation`
  - `CoreTruthDraft`
  - `TruthDraft`
  - `KeyFactsDraft`
  - `SurfaceStoryDraft`
  - `ForbiddenAssumptionsDraft`
  - `PuzzleReviewResult`
- 新增 `[puzzle_generation]` config：
  - `reviewer_enabled`
  - `deterministic_gate_enabled`
  - `max_revision_rounds`
  - `strict_surface_story_max_chars`
  - `strict_truth_min_chars`
  - `strict_truth_max_chars`
- 將題目生成拆成節點：
  - `interpret_topic`
  - `generate_core_truth`
  - `expand_truth`
  - `extract_key_facts`
  - `write_surface_story`
  - `generate_forbidden_assumptions`
  - `review_puzzle`
  - `finalize_puzzle`
- 實作 deterministic gate：
  - 檢查字數、空欄位、條數。
  - 檢查謎面是否含明顯解釋詞。
  - 檢查謎面是否疑似包含多個主要異常。
- 實作 reviewer routing：
  - `generate_core_truth`
  - `expand_truth`
  - `extract_key_facts`
  - `write_surface_story`
  - `generate_forbidden_assumptions`
- 每次 revision 增加 `revision_count`，超過上限後回 `LLM_OUTPUT_INVALID`。
- Graph 完成後只輸出正式 `Puzzle`，中間 draft 不進 API response 或 storage。
- raw message log 記錄中間 draft、reviewer issues、revision instruction。

模組交界：

- API 與 frontend 不變。
- GameService 仍只接收最終 `Puzzle`。
- `answer_question` 與 `judge_solution` 不接觸中間 draft。
- LLM client 負責 structured output retry；Graph 負責內容 revision retry。

驗收標準：

- fake LLM 測試可覆蓋 reviewer 失敗後重寫謎面並成功。
- fake LLM 測試可覆蓋 reviewer 要求重生核心真相。
- deterministic gate 可阻擋過長謎面與空 key facts。
- revision 超過上限時回 `LLM_OUTPUT_INVALID`。
- 進行中遊戲 API 仍不洩漏 `truth`、`key_facts`、`forbidden_assumptions`。
- 以真實 Ollama 人工測試 `便利商店` 與 `當兵期間操課`，不應再出現謎面客觀事實被 truth 否定的題目。
- `uv run pytest` 通過。

## 建議實作順序摘要

1. 資料模型與錯誤格式。
2. 設定、health、storage。
3. LLM client 與 fake LLM。
4. LangGraph workflow。
5. Game service。
6. REST API。
7. 前端 API client 與狀態。
8. 目前遊戲 UI。
9. 歷史紀錄 UI。
10. 真實 Ollama 整合與 prompt 調整。
11. Logging 與可觀察性。
12. 題目生成 pipeline 重構。
13. README 與文件整理。

## 每階段完成定義

每個階段結束前應確認：

- 對應文件中的行為已實作。
- 測試覆蓋該階段新增的核心分支。
- 沒有引入不必要的跨層依賴。
- `uv run pytest` 通過。
- 若牽涉前端，`npm run build` 通過。
- Git working tree 中沒有 `.venv`、`node_modules`、`dist`、`data/games/*.json` 等環境產物。
