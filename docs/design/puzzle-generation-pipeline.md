# 題目生成 Pipeline 重構設計

## 背景

目前題目生成由單一 `generate_puzzle` LLM 呼叫一次產生完整題目：

- `title`
- `surface_story`
- `truth`
- `key_facts`
- `forbidden_assumptions`
- `difficulty`

這個設計在模型能力有限時容易出現下列問題：

- 謎面、真相、關鍵事實彼此不一致。
- 謎面把錯誤推論寫成客觀事實，導致後續問答看起來像主持人否定謎面。
- 短主題會被模型過度發散，補出多餘角色、道具或流程。
- `key_facts` 有時不是解答判定用的因果鏈，而是故事摘要或氣氛描述。
- prompt 自檢不穩定，模型即使產生不合理題目也會通過 structured output。

因此題目生成應改成多節點 pipeline：先建立核心真相，再逐步擴寫、抽取、撰寫謎面，最後由能看見所有內容的 reviewer agent 進行一致性與合理性審核。

第三輪 contract prompt 測試補充顯示：pipeline 拆分能降低單節點負擔，但模型能力仍是題目品質的關鍵因素。`gemma4:e4b` 在短主題下仍容易產生不可玩的抽象原因或專業流程；`qwen3.6-35b-a3b` via llama.cpp OpenAI-compatible API 則能在相同 contract prompt 下產生更合理的核心因果。生成時間約 10 分鐘，目前視為可接受的品質 tradeoff。

## 設計目標

- 讓每個 LLM 節點只負責一件事，降低單次生成負擔。
- 先固定可解的核心因果鏈，再產生玩家可見謎面。
- `key_facts` 從真相抽取，不讓模型自由另創。
- 謎面只描述可觀察的客觀現象，不描述稍後會被真相否定的推論。
- reviewer 能看見完整內容，檢查一致性、可玩性與主題忠實度。
- reviewer 失敗時回到指定節點修正，而不是每次整題重生。
- retry 次數由 config 控制，避免無限修正。
- 支援較慢但較高品質的本地模型；題目生成優先追求可玩性與一致性，而非低延遲。

## 非目標

第一版重構不做：

- 多 agent 彼此對話式辯論。
- 人工審題 UI。
- 長期保存每次 draft 到正式遊戲紀錄。
- 對所有主題保證高品質，只先讓明顯不合理題目能被擋下並重試。

中間 draft 與 reviewer 結果可以寫入 raw message log，供本機除錯。

## 模型與耗時策略

題目生成是每局開始前的一次性流程。若模型需要較長時間才能產生高品質題目，目前接受此成本：

- 主要生成模型建議使用 `qwen3.6-35b-a3b`，透過 llama.cpp OpenAI-compatible API 呼叫。
- `request_timeout_seconds` 建議提高到至少 `600` 秒。
- OpenAI-compatible request 不應預設限制 `max_tokens`；Qwen reasoning 可能消耗大量 token，限制過低會截斷 JSON content。
- `gemma4:e4b` 可保留作為 fallback 或輕量判定任務候選，但不應作為短主題題目生成品質的主要依據。

後續若需要改善體感速度，應優先在前端顯示「題目生成中」狀態，或把較輕節點分配給較快模型，而不是降低題目生成品質標準。

## Pipeline 總覽

```text
topic
  -> interpret_topic
  -> generate_core_truth
  -> expand_truth
  -> extract_key_facts
  -> write_surface_story
  -> generate_forbidden_assumptions
  -> review_puzzle
      passed=true  -> finalize_puzzle
      passed=false -> route_revision
                         -> generate_core_truth
                         -> expand_truth
                         -> extract_key_facts
                         -> write_surface_story
                         -> generate_forbidden_assumptions
```

`finalize_puzzle` 才會輸出正式 `Puzzle`。前端與既有 API 仍只收到 `surface_story`。

## Graph State

建議新增專用 state，例如 `PuzzleGenerationState`。

```text
topic: str
topic_interpretation: TopicInterpretation | None
core_truth: CoreTruth | None
truth: str | None
key_facts: list[str]
surface_story: str | None
forbidden_assumptions: list[str]
difficulty: Difficulty
review_result: PuzzleReviewResult | None
review_issues: list[str]
revision_count: int
last_failed_node: str | None
final_puzzle: Puzzle | None
```

正式 `GameSession` 不必保存全部中間欄位，只保存最後 `Puzzle`。若需要除錯，使用 logging raw message 保存完整過程。

## 節點責任

### `interpret_topic`

輸入：

- 玩家原始主題

輸出：

- `scene`
- `objects`
- `actors`
- `actions`
- `explicit_results`
- `hard_constraints`
- `open_space`

責任：

- 解析主題中必須保留的字詞與明確結果。
- 區分「玩家指定」和「模型可自由補充」的內容。
- 主題很短時，不硬補奇怪物件；只標記為開放場景。

範例：

```json
{
  "scene": "便利商店",
  "objects": [],
  "actors": [],
  "actions": [],
  "explicit_results": [],
  "hard_constraints": ["故事主要場景必須是便利商店"],
  "open_space": "可自行補一個日常異常，但不得引入大型系統或複雜犯罪"
}
```

### `generate_core_truth`

輸入：

- `topic`
- `topic_interpretation`

輸出：

- `one_sentence_truth`
- `cause`
- `actor`
- `action`
- `result`
- `misdirection`

責任：

- 先產生一句話可說完的核心真相。
- 只允許一條主因果鏈。
- 不寫完整謎面，不補長背景。

核心真相格式應接近：

```text
某人因為 X 做了 Y，導致玩家看到 Z，但玩家誤以為 W。
```

### `expand_truth`

輸入：

- `core_truth`
- `topic_interpretation`

輸出：

- `truth`

責任：

- 把一句話核心真相擴成完整真相。
- 只能補必要背景，不得新增第二個異常或第二條主線。
- 必須保留 `core_truth` 的因果鏈。

建議長度：

- 160 到 280 個中文字。

過長真相會鼓勵模型補出多餘設定。若 config 仍保留較大的 `truth_max_chars`，生成 pipeline 應在 prompt 或後處理中使用較嚴格上限。

### `extract_key_facts`

輸入：

- `truth`
- `core_truth`

輸出：

- `key_facts`

責任：

- 從 `truth` 抽取解答判定最低必要事實。
- 不創作新設定。
- 每條 key fact 必須是可被玩家猜中或用於判定解答的具體事實。

建議固定 4 到 5 條：

1. 真正原因。
2. 關鍵行動者。
3. 關鍵行動。
4. 造成謎面異常的結果。
5. 表面誤導點。

### `write_surface_story`

輸入：

- `truth`
- `key_facts`
- `topic_interpretation`

輸出：

- `surface_story`
- `title`

責任：

- 最後才寫玩家可見謎面。
- 只寫角色能客觀觀察到的現象。
- 不寫「其實不成立」的推論。
- 不解釋原因，不透露關鍵行動者的動機。

硬規則：

- 只能有一個主要異常。
- 若謎面寫「A 被移除」，truth 必須承認 A 真的被移除。
- 若真相只是角色誤認，謎面應寫「他以為 A 被移除」或「他看到某處少了某物」，不能寫成客觀事實「A 被移除」。
- 不得加入 truth 沒有解釋的新物件、新角色或新事件。

### `generate_forbidden_assumptions`

輸入：

- `truth`
- `key_facts`
- `surface_story`

輸出：

- `forbidden_assumptions`

責任：

- 列出客觀上不成立、但玩家可能誤判的原因。
- 不得否定玩家主題指定的事實。
- 不得列出 truth 本身成立的內容。

### `review_puzzle`

輸入：

- `topic`
- `topic_interpretation`
- `core_truth`
- `truth`
- `key_facts`
- `surface_story`
- `forbidden_assumptions`

輸出：

```json
{
  "passed": false,
  "severity": "major",
  "target_node": "write_surface_story",
  "issues": [
    "謎面把錯誤推論寫成客觀事實",
    "謎面包含兩個互不相關的異常"
  ],
  "revision_instruction": "保留同一個 truth，只重寫謎面為單一客觀異常。"
}
```

責任：

- 看見所有內容後進行一致性與可玩性檢查。
- 指定最小修正節點。
- 提供短而具體的修正指令。

Reviewer 不負責直接改寫正式題目，以免審核與創作混在一起。

## Review 檢查項目

### 一致性

- `surface_story` 的每個異常都能在 `truth` 中直接解釋。
- `surface_story` 沒有把錯誤推論寫成客觀事實。
- `key_facts` 都能在 `truth` 找到根據。
- `forbidden_assumptions` 沒有否定 truth 或玩家主題。

### 可玩性

- 核心真相能用一句話說完。
- 玩家能透過是非題逐步縮小範圍。
- 不是只靠冷知識、專業知識或任意猜測。
- 不是純氣氛短文或抽象評論。

### 簡潔性

- 只有一個場景。
- 只有一個主要異常。
- 主要角色最多 2 人。
- 沒有多餘外部顧問、系統、門禁、特殊設備等非必要設定。

### 主題忠實度

- 玩家主題中的明確物品、場景、動作、結果都有保留。
- 若主題只是一個場景，模型可以自由補一個異常，但不得讓補充設定蓋過場景本身。
- 若主題包含明確結果，例如「報警」「空白發票」「沒有 13 樓」，謎面與真相都必須直接處理該結果。

## Revision Routing

Reviewer 回傳 `target_node` 後，graph 依目標回退。

```text
target_node=generate_core_truth
  -> 重新生成 core_truth、truth、key_facts、surface_story、forbidden_assumptions

target_node=expand_truth
  -> 保留 topic_interpretation/core_truth，重寫 truth 後重抽 key_facts 與謎面

target_node=extract_key_facts
  -> 保留 truth，重抽 key_facts，重跑 reviewer

target_node=write_surface_story
  -> 保留 truth/key_facts，只重寫 surface_story，再重跑 reviewer

target_node=generate_forbidden_assumptions
  -> 只重寫 forbidden_assumptions，再重跑 reviewer
```

若 reviewer 無法明確指定節點，預設回到 `generate_core_truth`。

## Retry 與失敗策略

新增或沿用 config：

```toml
[puzzle_generation]
max_revision_rounds = 2
reviewer_enabled = true
deterministic_gate_enabled = true
strict_surface_story_max_chars = 120
strict_truth_max_chars = 280
```

策略：

- structured output retry 仍由 LLM client 處理。
- reviewer revision round 由 graph state 的 `revision_count` 控制。
- deterministic gate 失敗不需呼叫 reviewer，可直接回到指定節點或整題重試。
- 超過 `max_revision_rounds` 後回傳 `LLM_OUTPUT_INVALID`，前端顯示一般生成失敗訊息。

## Deterministic Gate

Reviewer 是 LLM，仍可能漏判。因此在 reviewer 前後都應有少量程式檢查。

建議第一版先做：

- `surface_story` 字數上限。
- `truth` 字數上限。
- `key_facts` 條數。
- `forbidden_assumptions` 條數。
- 空字串檢查。
- `surface_story` 不得包含「其實」「原來」「因為」「真相」等明顯解釋詞。
- `surface_story` 不得同時出現過多句子或多個強連接事件，例如「更奇怪的是」造成第二異常。

這些檢查不追求完整理解，只負責擋掉明顯違規。

## Structured Output Schema

建議新增 schema：

```text
TopicInterpretation
CoreTruthDraft
TruthDraft
KeyFactsDraft
SurfaceStoryDraft
ForbiddenAssumptionsDraft
PuzzleReviewResult
```

最後仍轉成既有 `Puzzle` schema。API 與 storage 不需要知道中間 draft。

## Logging

每個節點都應記錄：

- `puzzle_generation.node.started`
- `puzzle_generation.node.completed`
- `puzzle_generation.node.failed`

重要欄位：

- `request_id`
- `llm_call_id`
- `node`
- `revision_count`
- `duration_ms`
- `content_chars`
- `review_passed`
- `review_target_node`
- `issue_count`

Raw message log 應保存每次中間 draft、reviewer issues 與 revision instruction。這些內容包含完整謎底，仍不進 git。

## 測試策略

### 單元測試

- deterministic gate 可阻擋過長謎面。
- deterministic gate 可阻擋空 key facts。
- reviewer routing 能正確回到指定節點。
- revision 超過上限時回 `LLM_OUTPUT_INVALID`。
- final puzzle 仍符合既有 API 不洩漏答案規則。

### Fake LLM Graph 測試

- 第一次 reviewer 失敗，指定重寫 `write_surface_story`，第二次通過。
- 第一次 reviewer 失敗，指定重寫 `generate_core_truth`，後續節點全部重跑。
- structured output retry 與 reviewer revision round 彼此獨立。

### 真實 Ollama 人工驗收

至少使用下列主題：

- `便利商店`
- `當兵期間操課`
- `空白發票`
- `電梯停在 13 樓但大樓沒有 13 樓`
- `一名男子每天買同一款便當直到店員報警`

每題人工確認：

- 謎面只有一個主要異常。
- 真相能一句話概括。
- 謎面不否定真相，也不被真相否定。
- key facts 是判定解答用的必要因果鏈。
- 第一個自然問題能得到合理的「是／否／無關」。

## 實作順序建議

1. 新增 draft schema 與 deterministic gate。
2. 將既有 `generate_puzzle` 拆成多個 LLM client method。
3. 新增 `PuzzleGenerationState`。
4. 實作 LangGraph 節點與 revision routing。
5. 更新 fake LLM 測試。
6. 補 reviewer prompt 與節點 log。
7. 用真實 Ollama 跑人工驗收並微調 prompt。

## 與既有流程的關係

對外 API 不變：

- `POST /api/games` 仍接收 topic。
- response 仍只回傳 `game_id`、`title`、`surface_story`、狀態與可見紀錄。
- 遊戲結束後 storage JSON 格式不變。

內部差異：

- 舊 `generate_puzzle` 節點改為「生成 pipeline 子圖」或多節點 graph。
- `Puzzle` 只在 `finalize_puzzle` 後建立。
- `answer_question` 與 `judge_solution` 使用最終 `Puzzle`，不接觸中間 draft。
