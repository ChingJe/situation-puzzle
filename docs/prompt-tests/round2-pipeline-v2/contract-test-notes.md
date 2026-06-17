# Pipeline v2 Contract Prompt 測試紀錄

更新時間：2026-06-16

## 測試目的

依據 `docs/design/prompt-contract.md`，驗證拆分後的題目生成 pipeline 是否能穩定產生：

- 短主題下不捏造使用者未提供的限制。
- 以人物行為異常為核心，而不是店務流程、商品狀態或專業制度。
- truth 不新增第二主線或抽象背景。
- surface story 僅呈現 2 句玩家可見異常，不洩漏原因。
- reviewer 能給出可操作的 target node 與 revision instruction。

## 測試環境

- Model: `gemma4:e4b`
- Base URL: Windows Ollama via WSL host IP
- Topic: `便利商店`
- Tool: `tools/pipeline_prompt_lab.py`

後續追加測試：

- Model: `qwen3.6-35b-a3b`
- Runtime: llama.cpp OpenAI-compatible API
- Base URL: `http://192.168.192.1:18080/v1`

## 本輪新增測試 variants

- `interpret_topic.v1-contract`
- `interpret_topic.v2-minimal-contract`
- `interpret_topic.v3-short-topic-contract`
- `generate_core_truth.v4-contract`
- `generate_core_truth.v5-contract`
- `generate_core_truth.v6-minimal-contract`
- `generate_core_truth.v7-concrete-contract`
- `expand_truth.v1-contract`
- `expand_truth.v2-minimal-contract`
- `expand_truth.v3-concrete-contract`
- `write_surface_story.v8-contract`
- `write_surface_story.v9-minimal-contract`
- `review_puzzle.v1-contract`

## Run 結果

| Run | Prompt set | Status | Target | 重點結果 |
| --- | --- | --- | --- | --- |
| 1 | core v4 / expand v1 / surface v8 / review v1 | `needs_non_surface_revision` | `expand_truth` | truth 373 字，超過 gate；core 漂到食品檢測、批次、過敏原等專業流程。 |
| 2 | interpret v1 / core v5 / expand v1 / surface v8 / review v1 | `needs_non_surface_revision` | `expand_truth` | deterministic gate 通過，但 truth 使用身份/狀態驗證流程，surface 洩漏目的；reviewer 打回 expand。 |
| 3 | interpret v2 / core v6 / expand v2 / surface v9 / review v1 | `needs_non_surface_revision` | `generate_forbidden_assumptions` | 格式與 gate 通過，但 interpret_topic 捏造大量角色、物品與 hard constraints；core/truth 使用「熟人秘密」「絕對保密」等模糊原因。 |
| 4 | interpret v3 / core v7 / expand v3 / surface v9 / review v1 | `revision_exhausted` | `write_surface_story` | interpret_topic 首次符合短主題 contract，但 core 因果仍不合理；reviewer 要求 surface 補「連續三次」，surface revision 無法收斂。 |
| 5 | Qwen llama.cpp + interpret v3 / core v7 / expand v3 / surface v9 / review v1 | `ok` | `finalize_puzzle` | 產生可玩的日常人物行為異常：丈夫買水後只拿收據不拿商品，為向妻子證明行蹤。deterministic gate 與 reviewer 均通過。耗時約 605 秒。 |

## 主要觀察

### 1. `interpret_topic` 需要更強約束，甚至可考慮 deterministic fallback

`interpret_topic.v1` 和 `v2` 仍會在短主題 `便利商店` 下捏造角色、物品與 hard constraints。

`interpret_topic.v3-short-topic-contract` 明確要求短主題輸出空 objects/actors/explicit_results，並固定 hard constraint 後，才符合 contract。

結論：短主題解析不應完全依賴 LLM 自由輸出。實作上可考慮：

- 對「短場景/短物品」主題走 deterministic interpretation。
- 或在 `interpret_topic` 後增加 deterministic cleanup，移除空字串與使用者未指定的 hard constraints。

### 2. `generate_core_truth` 是目前最大風險點

即使加入 contract，模型仍常把原因漂成：

- 食品檢測、批次、過敏原。
- 身份/狀態驗證流程。
- 某個熟人秘密、絕對保密私人事務。
- 不夠具體或不可判定的抽象動機。

`generate_core_truth.v7` 避開部分禁詞後，仍產出「買水但不能開門/開蓋」這種因果不清的題目。

結論：只靠 prompt 可能不足。需要在 core truth 後加入語意 gate 或獨立 reviewer，先審核 core 是否可玩，再進入 expand_truth。

### 3. `expand_truth` 會放大 core 的問題

當 core 不夠具體時，expand_truth 會把模糊原因擴寫成更大的背景，例如「驗證流程」「保密事務」「工作場所安全異常」。

結論：expand prompt 應保持嚴格，但更重要的是不要讓不合格 core 進入 expand。

### 4. `write_surface_story` 格式改善，但容易和 reviewer 目標衝突

`write_surface_story.v9` 配合新增 gate 可擋下「目的/為了/判斷/驗證」等洩漏詞。

但當 reviewer 要求補入「連續三次」這種 truth 中的重要資訊時，surface prompt 仍傾向維持單次事件，導致 revision exhausted。

結論：surface story 需要能呈現「一個重複行為形成的單一異常」，而不是只能寫單一時間點。

### 5. `review_puzzle` 仍不穩

第四筆中 reviewer `passed=false`，但 `revision_instruction` 為空字串。這違反 prompt contract，會讓 revision routing 無法得到可操作指令。

結論：需要 deterministic reviewer output validation：

- 若 `passed=false` 且 `issues=[]` 或 `revision_instruction` 空，視為 reviewer output invalid。
- 對此類情況重試 reviewer，或用 deterministic fallback 生成簡短 revision instruction。

## 初步結論

使用 `gemma4:e4b` 時，本輪尚未得到可直接採用的穩定 prompt set。

最有價值的測試結論是：

- `interpret_topic.v3-short-topic-contract` 的短主題規則可納入正式 prompt 或 deterministic preprocessing。
- `write_surface_story.v9-minimal-contract` 與新增 surface leak gate 可納入測試工具和正式 gate。
- `generate_core_truth` 需要比 prompt 更強的結構性防護，建議新增 `review_core_truth` 或 `core_truth_semantic_gate`。
- reviewer output 必須加 deterministic validation，否則 revision 可能空轉。

追加 Qwen 測試顯示，`qwen3.6-35b-a3b` 在相同 contract prompt 下可以產生明顯更合理的核心題目與完整 pipeline 結果。單局生成約 10 分鐘，這在目前產品定位下是可接受的 tradeoff：題目生成發生在開局前，品質、可玩性與可判定性比低延遲更重要。

llama.cpp 的 Qwen reasoning 會消耗大量輸出時間；`max_tokens` 過低會導致 JSON content 被截斷，因此目前測試需不限制 `max_tokens`，或另行找到可靠的 no-thinking 設定。

## 建議下一步

1. 先重構 pipeline，在 `generate_core_truth` 後加入 core-level semantic gate 或 LLM reviewer。
2. 對短主題實作 deterministic interpretation fallback。
3. 將 surface leak gate 加入正式 deterministic gate。
4. 補 reviewer output validation。
5. 完成以上結構性調整後，再跑 `便利商店` 5 次 acceptance，以及完整 regression topics。

目前建議採用 Qwen 作為主要生成模型，並先新增 OpenAI-compatible backend 支援與長 timeout 設定，再用少量但具代表性的 regression topics 驗證品質。`gemma4:e4b` 可保留為 fallback、輕量任務或對照測試；若未來仍希望以 `gemma4:e4b` 生成題目，才需要優先投入 core-level gate 與 deterministic fallback。
