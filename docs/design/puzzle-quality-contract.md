# 題目品質與解答判定 Contract

## 背景

近期實測顯示，即使題目生成 pipeline 已拆成多節點，仍可能產生「一致但不好玩」的題目。典型案例是便利商店題目：

- 謎面、真相與 key facts 彼此一致。
- 真相是「店員只是在正常補貨」。
- 玩家問到「是否正常補貨」後提交簡短解答，卻被判未解開。

這代表問題不只是 prompt 表述，而是目前正式 `Puzzle` 結構沒有明確區分：

- 題目的核心謎團是什麼。
- 哪些事實是玩家解答必須命中的。
- 哪些事實只是支撐問答與完整真相。
- Reviewer 要用什麼標準擋下低可玩性題目。
- Judge solution 要如何結合既有問答判斷玩家是否已經理解真相。

本文件定義下一版題目資料與流程 contract。後續 prompt、LangGraph 節點、Pydantic schema、reviewer 與測試都應以此為依據。

## 設計目標

- 讓題目品質不只依賴 prompt 文字，而是由 schema 和流程共同約束。
- 將「可玩性」變成可檢查的結構欄位。
- 將解答判定從「覆蓋所有 key facts」改成「命中 required solution facts」。
- 讓既有問答紀錄可以輔助判定玩家是否已解開。
- 保留目前 API 不暴露答案的行為；內部 log 與結束後紀錄可以保存完整資料。

## 非目標

第一版不做：

- 自動產生多題並由玩家挑選。
- 人工審題後台。
- 對任意短主題保證高品質。
- 使用向量資料庫或長期題庫。

## Puzzle V2 Schema

正式題目建議升級為 `PuzzleV2`。欄位可以先在後端內部使用，再逐步反映到儲存 JSON。

```json
{
  "schema_version": 2,
  "title": "便利商店的收據",
  "surface_story": "玩家可見謎面。",
  "core_mystery": "玩家需要解開的表面矛盾。",
  "core_truth": "一句話核心真相。",
  "truth": "完整真相。",
  "required_solution_facts": [
    {
      "id": "cause",
      "fact": "必要事實一",
      "role": "cause"
    },
    {
      "id": "action",
      "fact": "必要事實二",
      "role": "action"
    },
    {
      "id": "result",
      "fact": "必要事實三",
      "role": "result"
    }
  ],
  "supporting_facts": [
    {
      "id": "context_1",
      "fact": "支撐問答但不要求玩家提交時完整重述的事實。"
    }
  ],
  "misleading_assumptions": [
    "玩家容易誤會但客觀上不成立的方向"
  ],
  "forbidden_assumptions": [
    "問答時必須否定的不成立假設"
  ],
  "quality_notes": {
    "abnormal_result": "謎面中可觀察的反常結果",
    "misdirection": "表面最容易誤判的方向",
    "answer_shape": "玩家合理正解應該長什麼樣子"
  },
  "difficulty": "medium"
}
```

### 欄位責任

`surface_story`

- 玩家唯一可見的謎面。
- 只描述客觀現象或角色明確以為的事。
- 不揭露真正原因。

`core_mystery`

- 對內描述「這題到底要玩家解什麼」。
- Reviewer 用它檢查謎面是否有明確問題。
- 不直接回傳給玩家。

`core_truth`

- 一句話核心真相。
- 應符合「某人因為 X 做了 Y，導致玩家看到 Z，但玩家誤以為 W」。
- 若 `core_truth` 很普通，例如「店員只是在正常補貨」，reviewer 應打回。

`truth`

- 完整真相。
- 支撐所有是／否／無關問答。
- 可以比玩家最終答案更完整。

`required_solution_facts`

- 玩家解答必須命中的最低必要事實。
- 建議 3 到 4 條。
- 不應包含過細背景、場景常識或非核心心理推測。
- Judge solution 的主要判定依據。

`supporting_facts`

- 可以用於問答與完整揭示。
- 玩家最終解答沒有逐字說出時，不應直接導致失敗。
- 可包含動機背景、時間順序、角色誤判來源等。

`misleading_assumptions`

- 題目設計上希望玩家一開始可能猜錯的方向。
- Reviewer 用它檢查謎面是否有誤導但不暴雷。

`forbidden_assumptions`

- 客觀不成立，問答時應回答「否」的假設。
- 可由 `misleading_assumptions` 派生，但不必完全相同。

`quality_notes`

- 不參與玩家顯示。
- 用於 reviewer、prompt testing、log 分析。

## Required Solution Facts 設計規則

`required_solution_facts` 不是 truth 摘要，而是通關最低門檻。

合格 required facts 應包含：

- 真正原因：為什麼會發生反常結果。
- 關鍵行動：誰做了什麼。
- 表面結果：這個行動造成玩家看到什麼。
- 誤導校正：玩家原先可能以為的方向哪裡錯。

不應放入 required facts：

- 純背景，例如「故事發生在打烊後」。
- 過細觀察，例如「顧客看到店員從紙箱拿商品」。
- 不影響正解的心理描述，例如「顧客不熟悉打烊後流程」。
- 已可由其他 required fact 推出的重複事實。

便利商店失敗案例中，若保留原題，較合理分層會是：

```json
{
  "required_solution_facts": [
    {
      "id": "real_action",
      "fact": "店員實際上是在正常補貨，不是在偷竊。",
      "role": "action"
    }
  ],
  "supporting_facts": [
    {
      "id": "customer_misread",
      "fact": "顧客把補貨動作誤認為店員把商品塞進口袋。"
    },
    {
      "id": "after_hours_context",
      "fact": "誤會源於顧客不熟悉打烊後補貨流程。"
    }
  ]
}
```

但此題仍應由 reviewer 擋下，因為核心解答過於直覺。

## 可玩性 Gate

Reviewer 應新增「低可玩性 gate」。只要命中重大問題，即使一致性通過也不得 finalize。

### 必須通過

- 有一個明確、可觀察、值得追問的反常結果。
- 反常結果主要來自人物行動，而不是商品狀態、店務流程或場景雜亂。
- 正解不是一句最直覺的日常流程，例如「只是在補貨」「只是在打掃」「只是看錯」。
- 真相包含具體關鍵物件或行動條件。
- 玩家至少需要確認兩個以上不同面向，才會自然接近正解。

### 應打回 `generate_core_truth`

- 主線只是正常工作流程被誤會。
- `core_truth` 可以被一句常識回答直接命中。
- `abnormal_result` 是物品擺放或場景狀態，而不是人物行為或明確結果。
- `core_mystery` 不清楚，無法回答「玩家到底要解什麼」。
- 正解缺少轉折，只是補充背景常識。

### 應打回 `extract_solution_facts`

- 題目本身可玩，但 required facts 過多。
- required facts 把 supporting facts 當成通關門檻。
- required facts 沒有覆蓋真正原因或關鍵行動。

### 應打回 `judge_solution_prompt`

- 題目與 required facts 合理，但玩家命中必要事實仍被判失敗。
- 判定沒有使用既有問答紀錄。

## Pipeline 調整

建議將現有 `extract_key_facts` 拆成兩個責任更清楚的節點。

```text
topic
  -> interpret_topic
  -> generate_core_truth
  -> expand_truth
  -> extract_solution_facts
  -> write_surface_story
  -> generate_assumptions
  -> review_puzzle_quality
      passed=true  -> finalize_puzzle
      passed=false -> route_revision
```

### `extract_solution_facts`

輸入：

- `core_truth`
- `truth`

輸出：

- `required_solution_facts`
- `supporting_facts`

責任：

- 將通關必要事實與支撐事實分開。
- 不新增 truth 沒有的內容。
- 每個 required fact 必須能被玩家自然說出。
- 每個 supporting fact 可以用來回答問題，但不應成為硬性通關條件。

### `generate_assumptions`

輸入：

- `surface_story`
- `truth`
- `required_solution_facts`
- `supporting_facts`

輸出：

- `misleading_assumptions`
- `forbidden_assumptions`

責任：

- `misleading_assumptions` 服務題目設計與 reviewer。
- `forbidden_assumptions` 服務 yes/no 問答。

### `review_puzzle_quality`

輸入完整內容：

- `topic`
- `topic_interpretation`
- `core_mystery`
- `core_truth`
- `truth`
- `required_solution_facts`
- `supporting_facts`
- `surface_story`
- `misleading_assumptions`
- `forbidden_assumptions`

輸出：

```json
{
  "passed": false,
  "severity": "major",
  "target_node": "generate_core_truth",
  "issues": [
    "核心解答只是正常補貨，玩家可以用最直覺常識直接命中。"
  ],
  "revision_instruction": "保留便利商店場景，重新設計一個人物行為異常。真相必須包含具體物件或行動條件，不得以正常補貨、打掃、盤點或陳列作為解法。"
}
```

## Judge Solution 調整

`judge_solution` 不應再要求玩家覆蓋完整 `truth` 或所有 `key_facts`。

建議輸入：

- 玩家提交的 `solution`
- `required_solution_facts`
- `supporting_facts`
- `truth`
- 已有問答紀錄

判定原則：

- 玩家答案本身命中所有 required facts，判 `solved=true`。
- 玩家答案命中主要 required facts，且缺少內容已在既有問答中被確認，可判 `solved=true`。
- 玩家答案只說出 supporting facts，沒有命中真正原因或關鍵行動，判 `solved=false`。
- 玩家答案與 forbidden assumptions 衝突，判 `solved=false`。
- 未解開時仍只回傳固定訊息「尚未解開」，不提示缺少事實。

建議 structured output：

```json
{
  "solved": true,
  "matched_required_fact_ids": ["cause", "action", "result"],
  "matched_from_history_fact_ids": ["misdirection"],
  "conflicting_assumptions": [],
  "internal_reason": "玩家提交內容命中核心行動與真正原因，誤導校正已由先前問答確認。"
}
```

API 仍只回傳：

```json
{
  "solved": true
}
```

內部欄位可寫入 raw message log 或 solution attempt debug 欄位，但不顯示給玩家。

## 向後相容策略

第一階段可以同時保留舊欄位：

```json
{
  "key_facts": [
    "由 required_solution_facts 和 supporting_facts 合併出的 legacy 欄位"
  ],
  "required_solution_facts": [],
  "supporting_facts": []
}
```

相容規則：

- 新流程產生 `PuzzleV2`。
- 若舊程式仍需要 `key_facts`，由 `required_solution_facts + supporting_facts` 轉出。
- `answer_question` 可先繼續讀 `truth`、`key_facts`、`forbidden_assumptions`。
- `judge_solution` 優先使用 `required_solution_facts`；缺少時退回舊 `key_facts`。
- 歷史 JSON 可保留原格式，不需要一次 migration。

## 測試案例

### 低可玩性題目應被擋下

輸入主題：

```text
便利商店
```

不合格核心：

```text
店員打烊後整理貨架，顧客誤以為他偷竊。
```

Reviewer 應回：

- `passed=false`
- `target_node=generate_core_truth`
- issue 指出「正常補貨 / 店務流程 / 直覺解答」

### 短解答應可結合問答通關

已確認問答：

- 店員沒有偷竊：是
- 店員是在正常補貨：是

玩家提交：

```text
店員就只是在正常補貨
```

若此題已被允許進入遊戲，且唯一 required fact 是「正常補貨而非偷竊」，應判 `solved=true`。

但在新 reviewer 規則下，此題理想上不應進入遊戲。

## 實作順序建議

1. 新增 `PuzzleV2`、`SolutionFact`、`PuzzleQualityNotes` schema。
2. 將 `extract_key_facts` 改為 `extract_solution_facts`，同時輸出 legacy `key_facts`。
3. 更新 reviewer prompt，加入低可玩性 gate 與 required/supporting facts 檢查。
4. 更新 `judge_solution` prompt 與 schema，使其回傳 matched fact ids。
5. 補 fake LLM 測試：低可玩題被打回、required facts 過嚴被打回、短解答結合歷史可通關。
6. 使用真實 Qwen provider 重跑 `便利商店`、`空白發票`、`每天買同一款便當直到店員報警`。

## 決策

下一輪實作優先處理 data structure，再處理 pipeline routing，最後調整 prompt 文字。Prompt 必須服務 schema 與流程，不應再單獨承擔題目品質控制。
