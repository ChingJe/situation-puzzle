# 遊戲流程與 LangGraph 設計

## 遊戲狀態

遊戲狀態包含三種：

- `playing`：進行中。
- `solved`：玩家成功解開。
- `abandoned`：玩家放棄並查看答案。

第一版沒有失敗狀態，玩家可以無限提問。

## LangGraph 節點

### `generate_puzzle`

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
- `truth`、`key_facts`、`forbidden_assumptions` 僅供後端判定使用。
- 謎面不得直接暴露答案。

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
topic -> generate_puzzle -> memory session -> response(surface_story)
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

使用 LangChain `ChatOllama.with_structured_output(...)` 搭配 Pydantic schema。

設計原則：

- 每種 LLM 任務都有獨立 schema。
- LLM service 層負責 structured output retry。
- Graph node 不直接處理 JSON 修補細節。
- Pydantic 驗證失敗時依照 config retry。
- retry 後仍失敗則回傳 `LLM_OUTPUT_INVALID`。

## Retry 分層

- Request retry：Ollama API timeout、連線錯誤、5xx 類錯誤。
- Structured output retry：模型有回應，但無法解析或不符合 schema。

