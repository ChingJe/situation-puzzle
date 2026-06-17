# Round 4 Prompt 測試紀錄

更新時間：2026-06-17T11:07:19+08:00

## 範圍

- 測試 `write_surface_story.v10-objective-guard` 是否避免未被 truth 支持的絕對客觀謎面。
- 測試 `review_puzzle.v2-objective-claim-check` 是否能打回強客觀詞錯誤。
- 測試 `extract_solution_facts.v2-minimum-required` 是否把 required facts 收斂到最低通關門檻。

## Core Truth Active Cause

- Runs: 3
- Passed: 2
- Failed checks: {"core_truth_low_playability_terms": 1}

## Surface Objective Gate

- Runs: 3
- Passed: 3
- Failed checks: {}

## Reviewer Objective Claim Detection

- Bad absolute cases: 1
- Detected: 1
- Qualified false kills: 0

## Solution Facts Minimum Required

- Runs: 3
- Required fact counts: [3, 3, 3]
- Count pass: 3

## Full Pipeline Smoke

- Runs: 1
- Status ok: 1
- Surface gate passed: 1
- Reviewer passed: 0

## 人工觀察

### 1. `generate_core_truth.v8-active-cause` 有改善但不穩

core-only 便利商店測試 3 次中 2 次通過 gate，1 次仍被 `core_truth_low_playability_terms` 擋下。

通過案例多數轉向「買了不拿」「留下交易憑證」「可見訊號」等人物行為異常，比正式 prompt 產生的「顧客誤讀標籤，以為試吃區」更接近可玩題目。

但人工檢查仍有兩個風險：

- 有些通過案例的生活理由稍微牽強，例如為了報銷反覆購買但不帶走商品，雖然可推理，但玩家可能覺得動機不自然。
- 失敗案例表示 prompt 約束仍不足以完全阻止商品擺放、標籤、誤會類核心回流，正式實作時仍應搭配 core-level semantic gate 或 reviewer。

結論：`v8-active-cause` 可作為下一版 `generate_core_truth` 的基礎，但不宜單靠 prompt 放行。

### 2. `write_surface_story.v10-objective-guard` 有效但不充分

固定便利商店回歸案例中，3 次 surface 輸出都通過原始 gate，且沒有重現原始問題中的「全程無人靠近」客觀斷言。

但人工檢查發現兩個新問題：

- 第 1 次輸出直接寫出「顧客趁店員注視門口時將商品藏入外套」，這會提前洩漏核心解法。`write_surface_story` 仍需要更強的「不可寫出關鍵行動者與關鍵行動」規則。
- 第 3 次輸出使用簡中 `凭空消失`，並寫「無人靠近時」。原始 gate 沒有抓到 `凭空`、`無人靠近`、`無人接近` 這類變體，因此 lab gate 已補上繁簡體與近義詞檢查，後續正式 gate 也應同步。

結論：objective guard 方向正確，但應和 `solution-leak guard` 一起實作，不能只處理絕對客觀詞。

### 3. `review_puzzle.v2-objective-claim-check` 初步通過

reviewer 測試中：

- 原始 bad surface：成功打回 `write_surface_story`。
- 視角限定版 surface：沒有被誤殺。

這代表 reviewer 能理解「絕對客觀敘述」與「視角限定敘述」的差異，可納入正式 prompt 調整候選。

### 4. `extract_solution_facts.v2-minimum-required` 初步通過

3 次輸出都穩定產生 3 條 required facts，並將誤導校正與執行細節多數放入 supporting facts。

這符合目前想要的通關判定方向：玩家只要說出真正原因、關鍵行動、造成的反常結果即可，不必完整重述所有誤導與監視器細節。

### 5. 完整 pipeline 的失敗點仍在上游核心真相

完整 pipeline smoke 的 surface gate 通過，但 reviewer 未放行。打回原因不是 objective-claim 問題，而是正式 `generate_core_truth` 仍產生「顧客誤讀標籤，以為試吃區」這類單純誤會題。

reviewer 判定：

- target node: `generate_core_truth`
- issue: 核心機制太接近「只是看錯／單純誤會」，可玩性不足。
- 另有 surface 小問題：謎面使用「退貨」但 truth 只是「放回冷櫃」，用詞不精確。

這延續先前結論：本輪 prompt 調整若只處理謎面客觀性，仍無法解決「核心真相太弱」問題。

## 初步結論

- 可採用方向：
  - `generate_core_truth.v8-active-cause` 的主動行動／隱藏條件規則。
  - `review_puzzle.v2-objective-claim-check`。
  - `extract_solution_facts.v2-minimum-required`。
  - `write_surface_story.v10-objective-guard` 的視角限定規則。
- 不能直接採用：
  - 只靠 prompt 的 core truth 放行，因為仍有弱核心回流。
  - 只靠 objective guard 的 surface prompt，因為仍可能洩漏核心行動。
- 下一步建議：
  - 正式 prompt 調整時同步改 `generate_core_truth`、`write_surface_story`、`review_puzzle`、`extract_solution_facts`。
  - deterministic gate 增加 `凭空/憑空`、`無人靠近/沒有人靠近/無人接近`、以及關鍵行動洩漏檢查。
  - 在 `generate_core_truth` 後新增 core-level semantic gate 或 reviewer，先擋掉「只是誤會／只是看錯／標籤貼錯」這類弱核心，再進入 expand_truth。
