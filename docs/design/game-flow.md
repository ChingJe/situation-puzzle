# 遊戲流程與 LangGraph 設計

## 遊戲狀態

遊戲狀態包含三種：

- `playing`：進行中。
- `solved`：玩家成功解開。
- `abandoned`：玩家放棄並查看答案。

第一版沒有失敗狀態，玩家可以無限提問。

## LangGraph 節點

### `generate_puzzle_pipeline`

輸入：

- 使用者主題
- 題目生成 config

輸出：

- `title`
- `surface_story`
- `truth`
- `key_facts`
- `forbidden_assumptions`
- `difficulty`

規則：

- 內容使用繁體中文。
- 玩家只會看到 `surface_story`。
- `truth`、`required_solution_facts`、`supporting_facts`、`forbidden_assumptions` 僅供後端判定使用。
- 謎面不得直接暴露答案。
- 題目生成不再由單一 LLM 呼叫一次完成，而是由多節點 pipeline 逐步產生與審核。
- 詳細節點與 revision loop 見 `docs/design/puzzle-generation-pipeline.md`。

內部子流程：

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

`review_puzzle` 不通過時，依 reviewer 指定的 `target_node` 回到最小必要節點修正。超過設定的 revision 次數後回傳 `LLM_OUTPUT_INVALID`。

### `answer_question`

輸入：

- 玩家問題
- 題目真相
- 關鍵事實
- 禁止假設
- 已有問答紀錄

輸出：

- `is_valid_question`
- `answer`: `yes | no | irrelevant`

規則：

- 若玩家輸入不是可用是／否回答的問題，回傳 `is_valid_question=false`。
- 有效問題只允許三種答案：`yes`、`no`、`irrelevant`。
- 前端顯示時轉為「是」「否」「無關」。
- 不補充說明，不提供提示。

### `judge_solution`

輸入：

- 玩家提交的完整解答
- `truth`
- `key_facts`
- 已有問答紀錄

輸出：

- `solved`: boolean

規則：

- 未解開時固定顯示「尚未解開」。
- 不提示缺少哪些 key facts。
- 解開時遊戲狀態轉為 `solved`，並可揭示 `truth`。

下一版若題目資料已升級為 `PuzzleV2`，`judge_solution` 應優先根據 `required_solution_facts` 判定，並允許使用已有問答紀錄補足玩家短解答缺少但已確認的核心事實。`supporting_facts` 不應作為硬性通關門檻。詳細規則見 `docs/design/puzzle-quality-contract.md`。

### `finalize_game`

輸入：

- 遊戲狀態
- 完整遊戲資料

輸出：

- 可持久化的遊戲紀錄

規則：

- `solved` 或 `abandoned` 時寫入 `data/games/{game_id}.json`。
- 進行中遊戲不寫入歷史 JSON。

## 主要流程

### 建立遊戲

```text
topic -> generate_puzzle_pipeline -> memory session -> response(surface_story)
```

### 提問

```text
question -> answer_question -> append question record -> response(answer)
```

若問題無效：

```text
question -> answer_question -> error(INVALID_QUESTION)
```

無效問題不加入正式問答紀錄。

### 提交解答

```text
solution -> judge_solution
  solved=false -> append attempt -> response("尚未解開")
  solved=true -> append attempt -> finalize_game -> response(truth)
```

### 放棄

```text
abandon -> status=abandoned -> finalize_game -> response(truth)
```

## Structured Output 策略

透過後端 LLM provider adapter 搭配 Pydantic schema 驗證。

Provider 策略：

- `ollama`：可使用 LangChain `ChatOllama.with_structured_output(...)`。
- `openai-compatible`：可呼叫 `/v1/chat/completions`，使用 `response_format={"type":"json_object"}`，再由後端以 Pydantic schema 驗證與轉型。

正式 graph node 只依賴 `LlmClient` 介面，不直接依賴 Ollama 或 llama.cpp 實作。

設計原則：

- 每種 LLM 任務都有獨立 schema。
- 題目生成 pipeline 的每個 draft 節點都有獨立 schema，最後才轉成正式 `Puzzle`。
- LLM service 層負責 structured output retry。
- Graph node 不直接處理 JSON 修補細節。
- Pydantic 驗證失敗時依照 config retry。
- retry 後仍失敗則回傳 `LLM_OUTPUT_INVALID`。

## Retry 分層

- Request retry：LLM provider API timeout、連線錯誤、5xx 類錯誤。
- Structured output retry：模型有回應，但無法解析或不符合 schema。
- Puzzle revision retry：reviewer 或 deterministic gate 判定內容不合格，回到指定生成節點重寫。
