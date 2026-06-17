# Pipeline v2 Prompt 測試摘要

更新時間：2026-06-16T18:16:40+08:00

## Baseline

- Runs: 12
- Status: {
  "revision_exhausted": 5,
  "ok": 5,
  "needs_non_surface_revision": 2
}
- Failed checks: {
  "surface_story_too_long": 4,
  "surface_story_sentence_count": 4,
  "surface_story_explains_cause": 2,
  "truth_too_long": 1
}

## Surface Story Candidates

### write_surface_story.v0

- Runs: 4
- Passed: 0 (0%)
- Failed checks: {
  "surface_story_sentence_count": 4,
  "surface_story_too_long": 3
}

### write_surface_story.v1

- Runs: 4
- Passed: 1 (25%)
- Failed checks: {
  "surface_story_sentence_count": 3,
  "surface_story_too_long": 2
}

### write_surface_story.v2

- Runs: 4
- Passed: 3 (75%)
- Failed checks: {
  "surface_story_explains_cause": 1
}

### write_surface_story.v3

- Runs: 4
- Passed: 0 (0%)
- Failed checks: {
  "surface_story_sentence_count": 4,
  "surface_story_too_long": 2,
  "surface_story_explains_cause": 1
}

### write_surface_story.v4

- Runs: 4
- Passed: 2 (50%)
- Failed checks: {
  "surface_story_sentence_count": 2
}

### write_surface_story.v5

- Runs: 4
- Passed: 4 (100%)
- Failed checks: {}

### write_surface_story.v6

- Runs: 6
- Passed: 6 (100%)
- Failed checks: {}

### write_surface_story.v7

- Runs: 6
- Passed: 6 (100%)
- Failed checks: {}

## 人工判讀

### 1. 正式 baseline 仍穩定失敗

`generate_core_truth.v0 + write_surface_story.v0` 針對 `便利商店` 跑 3 次，全部失敗：

- 3/3 `revision_exhausted`
- 3/3 target node 為 `write_surface_story`
- 主要 deterministic gate failure：
  - `surface_story_too_long`
  - `surface_story_sentence_count`
  - 少數包含 `surface_story_explains_cause`

這重現了前一次實際遊戲中的問題：正式 prompt 會把完整故事或多個事件段落塞進謎面，revision instruction 只說「太長／不是兩句」時，模型仍無法穩定收斂。

### 2. 單獨修謎面 prompt 可改善格式，但不足以改善可玩性

`write_surface_story.v5`、`v6`、`v7` 在固定 baseline truth/key_facts 的單節點測試中 gate 通過率最高：

- `v5`: 4/4 pass
- `v6`: 6/6 pass
- `v7`: 6/6 pass

其中 `v6/v7` 的有效規則是：

- 禁止新增 truth/key_facts 沒有的物品、人物、位置、聲音或第二異常。
- 禁止情緒與氣氛詞。
- 明確要求 2 句、無註解、無自檢文字、無 Markdown/HTML/XML。
- 第二句必須是客觀可見的反常結果。

但人工檢查顯示，即使 gate 通過，若上游 truth 本身不可玩，謎面仍會變成「回收區混亂」「包裝盒誤會」「商品並排」這類弱題。結論是：`write_surface_story` prompt 必須更新，但它不是唯一問題。

### 3. `core v2 + surface v7` 能建立成功，但故事仍偏弱

`generate_core_truth.v2 + write_surface_story.v7` 對 `便利商店` 跑 3 次：

- 3/3 pipeline 成功
- 3/3 無 deterministic gate failure
- 平均耗時約 151 秒

但人工品質檢查未通過：

- 仍產生打包、垃圾、陳列等店務流程題。
- 謎面可通過 reviewer，但反常性不足。
- reviewer 對「可玩性」與「是否只是店務流程」判斷過寬。

此組合可證明「較嚴格的 surface prompt 能降低格式失敗」，但不能作為最終穩定 prompt。

### 4. `core v3` 方向正確，但需要更嚴格的日常限制與 expand_truth 約束

`generate_core_truth.v3 + write_surface_story.v7` 對 `便利商店` 跑 3 次：

- 1/3 pipeline 成功
- 2/3 被打回 `expand_truth`
- 其中 1 筆 deterministic gate 標記 `truth_too_long`

人工檢查：

- `core v3` 成功把方向從店務流程轉向人物行為異常。
- 但 prompt 中允許「訊號」後，模型會走向秘密組織、任務暗號等不符合日常型限制的設定。
- `expand_truth` 會把簡單核心擴寫成過長、過戲劇化、或新增設定的故事。

此組合指出下一個主要調整點：

- `generate_core_truth` 要保留「人物行為異常」方向。
- 但必須禁止秘密組織、任務、暗號、犯罪集團、專業流程。
- `expand_truth` 必須禁止新增 core_truth 沒有的設定，並嚴格控制 160 到 280 字。

## 建議採用的 prompt 調整方向

### `generate_core_truth`

應從 `v3` 取用以下規則：

- 核心必須是人物行為異常，不是店內物品狀態異常。
- `abnormal_result` 必須描述某人做了看似不合理的行動、要求、說法或選擇。
- 玩家看見異常後，應能問「這個人為什麼要這樣做？」
- 禁止把商品擺錯、分類、庫存、打包、清潔、垃圾回收、陳列位置當作主線。

但需要新增更強限制：

- 禁止秘密組織、任務暗號、接頭、犯罪集團、專業流程。
- 若使用「訊號」，必須是家人、朋友、店員之間的日常提醒或求助，不得是組織任務。
- 真正原因必須是普通生活可理解的動機，例如證明時間、避免誤會、辨認身分、保護他人、求助。

### `expand_truth`

目前需要新增規則：

- 只能擴寫 core_truth，不得新增秘密組織、第二角色群、第二任務、專業制度。
- truth 必須維持一條核心因果鏈。
- truth 以 160 到 260 字為目標，不要靠近 280 字上限。
- 若 core_truth 涉及訊號或證明，必須明確說明「誰需要知道、為什麼需要知道、該行動如何被對方理解」。
- 不要把解釋寫成「資訊落差」這種抽象詞，必須落到具體原因。

### `write_surface_story`

建議以 `v7` 為基礎整合到正式 prompt：

- surface_story 內只能有 2 句中文句子。
- 不得有換行、Markdown、HTML、XML、註解、自檢文字或括號說明。
- 禁止情緒與氣氛詞。
- 只能使用 truth/key_facts 已存在的物品、標示、角色、行動與結果。
- 不得新增 truth/key_facts 沒有的線索或第二異常。
- 第一句建立普通期待，第二句呈現與期待不一致的可見結果。

### `review_puzzle`

reviewer 需要新增「可玩性」審核項目：

- 若主要異常只是商品擺放、打包、庫存、清潔、陳列、垃圾分類，必須打回 `generate_core_truth`。
- 若 surface_story 只是角色覺得困惑、疑慮、不安，而沒有客觀反常結果，必須打回 `write_surface_story`。
- 若 truth 引入秘密組織、任務暗號、專業流程或第二主線，必須打回 `expand_truth` 或 `generate_core_truth`。
- 若 reviewer issues 為空但 passed=false，應視為 reviewer output invalid，避免 `revision_instruction` 不可操作。

## 初步結論

本輪尚未得到可直接視為最終穩定的完整 prompt set。

已確認可採用的部分是：

- `write_surface_story.v7` 的格式與來源限制。
- `generate_core_truth.v3` 的「人物行為異常」方向。

尚未解決的部分是：

- `generate_core_truth` 仍需要禁止秘密組織/任務暗號並給出日常可玩模式。
- `expand_truth` 需要嚴格防止新增設定與過長。
- `review_puzzle` 需要更強的可玩性審核，不能只看一致性。

下一步應先調整 `generate_core_truth`、`expand_truth`、`write_surface_story`、`review_puzzle` 的正式 prompt，再用 `便利商店`、`當兵期間操課`、`電梯停在 13 樓，但大樓沒有 13 樓` 做 regression。
