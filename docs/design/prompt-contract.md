# Prompt Contract 與 Agent 責任設計

## 目的

本文件定義題目生成 pipeline 中每個 LLM agent 的 prompt contract。Contract 用來描述每個節點的目的、輸入邊界、輸出要求、禁止事項、常見失敗型態與 revision routing 原則。

後續正式 prompt 調整、prompt testing、deterministic gate 與 reviewer 規則都應以本文件為依據。

## 背景

第二輪 pipeline prompt testing 顯示：

- 只強化 `write_surface_story` 可以改善格式，但不能保證題目可玩。
- `generate_core_truth` 若沒有明確定義「可玩的核心異常」，短主題會被補成店務流程、陳列、庫存、清潔或分類問題。
- `expand_truth` 若邊界不清楚，會把簡單核心擴寫成秘密組織、任務暗號、專業制度或第二主線。
- `review_puzzle` 目前能檢查部分一致性，但對「一致但不好玩」的題目過寬。

因此 prompt 設計不應只列規則，而要先定義各 agent 的 contract：每個節點只負責一件事，且不得替其他節點完成工作。

後續 contract prompt 測試也顯示，contract 本身不能完全彌補模型能力差距。`gemma4:e4b` 即使套用更嚴格 contract，仍常在短主題下產生專業流程、抽象驗證或不可判定原因；`qwen3.6-35b-a3b` via llama.cpp OpenAI-compatible API 在相同方向下能產生更清楚的日常人物行為異常。此專案目前接受約 10 分鐘的開局生成時間，將題目品質視為比低延遲更高的優先級。

## 全域原則

### 語言與風格

- 所有玩家可見內容與內部故事內容以繁體中文為主。
- 題材偏日常型懸疑，避免露骨血腥。
- 不依賴醫療、法律、工程、金融或冷門專業知識。
- 不使用大型陰謀、秘密組織、未知科技、超自然、駭客、系統升級作為解法。

### 可玩性定義

合格題目必須同時滿足：

- 有一個玩家可見或可聽見的反常結果。
- 反常結果背後有一條普通生活常識可理解的核心因果鏈。
- 玩家可透過是／否／無關問答逐步確認角色、行動、原因、結果與誤導點。
- 最終正解可以用一句話概括。

建議核心形式：

```text
某人因為 X 做了 Y，導致玩家看到 Z，但玩家誤以為 W。
```

### 主要禁止方向

除非使用者主題明確指定，題目生成不得把下列內容作為主線：

- 商品擺放、商品分類、庫存盤點、打包方式、清潔、垃圾回收、陳列位置、促銷標籤。
- 角色只是困惑、疑慮、不安，沒有客觀反常行動或結果。
- 秘密組織、接頭、任務暗號、犯罪集團、專業流程、內部制度。
- 系統警報、自動偵測、駭客、模擬模式、未知科技。

若需要「訊號」或「暗示」，必須是日常場景中的人際行為，例如家人、朋友、同事、店員之間可理解的提醒、求助或證明，不得變成組織任務。

## Contract 概觀

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

每個節點都應遵守兩個原則：

- 只產生自己負責的內容，不預先替後續節點創作。
- 若收到 revision instruction，只修正該 instruction 指定的問題，不重寫無關內容。

## `interpret_topic`

### 目的

解析使用者主題，標記後續生成必須保留的元素與可自由補完的空間。

### 輸入

- 使用者原始 topic。

### 輸出

- `title`
- `scene`
- `objects`
- `actors`
- `explicit_results`
- `hard_constraints`
- `open_space`

### 責任邊界

應做：

- 保留使用者明確指定的場景、物品、角色、動作、結果。
- 區分「使用者已指定」與「模型可補充」。
- 若 topic 很短，只標記為開放場景，不自行創作真相。

不得做：

- 不得決定核心反轉。
- 不得補完整故事。
- 不得加入使用者沒有指定的限制，除非是全域安全/風格限制。

### 合格輸出特徵

對 `便利商店` 這類短主題，合格解析應接近：

```json
{
  "title": "便利商店",
  "scene": "便利商店",
  "objects": [],
  "actors": [],
  "explicit_results": [],
  "hard_constraints": ["故事主要場景必須是便利商店"],
  "open_space": "可補一個日常人物行為異常，但不得把主線寫成店務流程或複雜犯罪。"
}
```

### 常見失敗

- 在 `open_space` 中鼓勵「貨架擺設」「店內流程」等弱題材。
- 把短主題過度解讀成具體事件。
- 遺漏使用者明確指定的結果，例如「報警」「沒有 13 樓」。

## `generate_core_truth`

### 目的

產生可玩的核心謎題骨架。這是整個 pipeline 最重要的節點。

### 輸入

- `topic`
- `topic_interpretation`
- optional `review_instruction`

### 輸出

- `core_truth`
- `cause`
- `actor_action`
- `abnormal_result`
- `misdirection`

### 責任邊界

應做：

- 產生一條核心因果鏈。
- 讓 `abnormal_result` 成為玩家會想追問的「人物行為異常」。
- 明確交代真正原因、關鍵行動者、關鍵行動、表面異常、誤導點。

不得做：

- 不得寫完整真相段落。
- 不得寫玩家可見謎面。
- 不得把主線設成店務流程、商品狀態或場景混亂。
- 不得新增大型陰謀、秘密組織、任務暗號、犯罪集團、專業流程。

### 核心異常標準

合格的 `abnormal_result` 應描述人物行為，例如：

- 顧客買了商品卻故意不帶走。
- 店員拒絕賣出普通商品。
- 某人只拿收據不要商品。
- 店員因顧客每天買同一樣東西而報警。
- 顧客明明已結帳，卻要求重印一張看似無用的發票。

不合格的 `abnormal_result`：

- 貨架上的商品被放錯位置。
- 店內某個角落很亂。
- 包裝盒看起來像被拿走。
- 清潔工劃出待確認區。
- 角色覺得很困惑或不安。

### 合格輸出特徵

- `cause` 是真正原因，不是「誤會」「資訊落差」這種抽象詞。
- `actor_action` 是具體人物行動。
- `abnormal_result` 可直接成為謎面的核心異常。
- `misdirection` 指出玩家最可能猜錯的方向。

### 常見失敗

- 把 `便利商店` 補成庫存、清潔、打包、陳列問題。
- 因為 prompt 提到「訊號」，模型生成秘密組織或任務暗號。
- `core_truth` 太長，已經像完整真相。
- `abnormal_result` 是心理狀態，而非可觀察事件。

### Revision Routing

若發生下列問題，reviewer 應打回 `generate_core_truth`：

- 核心真相不可玩。
- 主線是店務流程或物品狀態。
- 真正原因依賴秘密組織、超自然、專業流程。
- 有多條核心因果鏈。
- `abnormal_result` 無法成為謎面核心。

## `expand_truth`

### 目的

把 core truth 擴寫成完整、可供問答與解答判定使用的 truth。

### 輸入

- `topic`
- `topic_interpretation`
- `core_truth`
- optional `review_instruction`

### 輸出

- `truth`

### 責任邊界

應做：

- 保留 core truth 的同一條因果鏈。
- 補足角色、原因、行動、結果、誤導點。
- 讓 truth 能支撐後續 yes/no/irrelevant 問答。

不得做：

- 不得新增第二主線。
- 不得新增 core truth 沒有的秘密組織、任務、制度、設備或外部角色群。
- 不得把題目擴寫成小說式背景。
- 不得改寫 core truth 的真正原因。

### 長度要求

建議目標：

- 160 到 260 個中文字。

接受範圍：

- 不低於 `strict_truth_min_chars`。
- 不高於 `strict_truth_max_chars`。

Prompt 應要求模型不要貼近上限，避免過度補設定。

### 合格輸出特徵

一段合格 truth 應能回答：

- 誰做了關鍵行動？
- 為什麼他要這樣做？
- 他具體做了什麼？
- 這造成謎面中的什麼反常結果？
- 玩家為什麼容易誤會？

### 常見失敗

- 把簡單 core truth 擴成秘密組織或任務暗號。
- 新增 core truth 沒有的人物群或制度。
- 使用「資訊落差」「保護性行為」等抽象詞，沒有具體因果。
- 字數過長，導致 reviewer 或 deterministic gate 打回。

### Revision Routing

若發生下列問題，reviewer 應打回 `expand_truth`：

- core truth 合理，但 truth 新增不必要設定。
- truth 超過長度限制。
- truth 與 core truth 不一致。
- truth 缺少原因、行動或結果。

若 core truth 本身不可玩，應打回 `generate_core_truth`，不要只要求 `expand_truth` 修補。

## `extract_solution_facts`

### 目的

從 core truth 與 truth 抽取玩家通關需要命中的最低必要事實，並把支撐問答但不要求玩家提交時完整重述的事實分開。

### 輸入

- `core_truth`
- `truth`

### 輸出

- `required_solution_facts`
- `supporting_facts`
- legacy `key_facts` 可在 finalize 階段由兩者合併產生

### 責任邊界

應做：

- 只從 truth 抽取。
- `required_solution_facts` 覆蓋通關最低必要因果鏈。
- `supporting_facts` 保存問答與完整揭示需要的背景，但不作為玩家提交解答的硬性門檻。
- 讓每條 required fact 都能被玩家自然說出，且可用於勝負判定。

不得做：

- 不得新增 truth 沒有的設定。
- 不得抽取氣氛、情緒、文學化描述。
- 不得把 supporting facts 或 forbidden assumptions 寫成 required facts。

### 建議結構

`required_solution_facts` 建議 2 到 4 條：

- 真正原因。
- 關鍵行動。
- 造成謎面異常的結果。
- 必要時加入表面誤導校正。

`supporting_facts` 可放：

- 動機背景。
- 時間順序。
- 角色誤判來源。
- 不影響通關門檻的執行細節。

### 合格輸出特徵

每條 required fact 都應能改寫成是非題，例如：

```text
店員拒絕賣商品，是因為他認出顧客正在用商品傳遞求助訊號。
```

可問：

```text
店員拒絕賣商品是因為他認出某種求助訊號嗎？
```

### 常見失敗

- 把整段 truth 摘要成長句。
- 抽出「顧客很焦慮」「場景很奇怪」等不可判定事實。
- 遺漏真正原因或關鍵行動。
- 把玩家不必完整重述的背景細節放入 required facts，導致解答判定過嚴。

### Revision Routing

若 required/supporting facts 遺漏、過多、過少、分層錯誤或新增設定，打回 `extract_solution_facts`。

若 truth 本身不清楚導致 facts 無法抽取，打回 `expand_truth`。

## `write_surface_story`

### 目的

把完整 truth 壓縮成玩家唯一可見的謎面。

### 輸入

- `topic`
- `topic_interpretation`
- `truth`
- `required_solution_facts`
- `supporting_facts`
- optional `review_instruction`

### 輸出

- `surface_story`

### 責任邊界

應做：

- 只描述玩家可觀察到的表面異常。
- 建立一個普通期待，再呈現與期待不一致的結果。
- 使用 truth、required/supporting facts 已存在的角色、物品、行動與結果。
- 為 required facts 中的真正原因留下至少一個公平、可觀察的入口。

不得做：

- 不得解釋原因。
- 不得寫真正原因、動機、關鍵行動者的內心或完整手法。
- 不得新增 truth、required/supporting facts 沒有的線索。
- 不得加入第二個異常。
- 不得輸出內部自檢、Markdown、HTML、XML、註解或括號說明。
- 不得使用「其實」「原來」「因為」「真相」。
- 不得用情緒或氣氛詞代替客觀異常，例如困惑、疑慮、不安、詭異、刺耳。

### 格式要求

- 剛好 2 句中文句子。
- 50 到 120 個中文字。
- 不換行。
- 第一句：角色在主題場景中根據某個可見資訊做出普通判斷或行動。
- 第二句：一個可見結果和第一句期待不一致。

### 合格輸出特徵

合格謎面應讓玩家只知道：

- 發生了什麼表面矛盾。
- 這個矛盾值得追問。

不應讓玩家知道：

- 真正原因。
- 誰故意做了關鍵行動。
- 後續如何解釋。

### 常見失敗

- 摘要完整 truth。
- 寫成 3 句以上。
- 加入模型自檢註解。
- 新增 truth 沒有的紙板、批次、聲音、角落物品。
- 把角色誤會寫成客觀事實。
- 完全沒有為真正原因留下可追問入口，例如 truth 是水管破裂但謎面沒有水痕、潮濕、天花板、滴水或相關現象。

### Revision Routing

若 surface story 格式錯、洩漏原因、新增線索、多異常，打回 `write_surface_story`。

若 surface story 很難寫，因為 truth 本身沒有明確反常結果，打回 `generate_core_truth` 或 `expand_truth`。

## `generate_assumptions`

### 目的

列出題目設計上的誤導方向，以及玩家容易錯猜且客觀上不成立的假設，協助問答、review 與解答判定。

### 輸入

- `truth`
- `required_solution_facts`
- `supporting_facts`
- `surface_story`

### 輸出

- `misleading_assumptions`
- `forbidden_assumptions`

### 責任邊界

應做：

- `misleading_assumptions` 描述謎面希望玩家一開始可能誤判的方向。
- 根據 truth 與 surface story 列出 2 到 3 條常見錯猜。
- 每條 forbidden assumption 都應是客觀上不成立的假設。

不得做：

- 不得否定使用者主題指定的事實。
- 不得否定謎面中客觀成立的事實。
- 不得列出 truth 其實成立的內容。
- 不得新增新劇情。

### 合格輸出特徵

例如謎面看似偷竊但 truth 是誤拿，合格 forbidden assumption 可是：

- 「有人故意偷走商品」
- 「店員刻意陷害顧客」

### 常見失敗

- 寫成提示。
- 否定謎面明確發生的事。
- 把角色曾經誤會過的內容當成 forbidden assumption，但該誤會本身是故事中成立的心理狀態。

### Revision Routing

若 assumptions 條數錯誤、否定主題/謎面事實，或把成立的誤導方向寫成 forbidden assumption，打回 `generate_assumptions`。

## `review_puzzle`

### 目的

審核整題是否適合進入遊戲，並指出最小必要修正節點。

### 輸入

- `topic`
- `topic_interpretation`
- `core_truth`
- `truth`
- `required_solution_facts`
- `supporting_facts`
- `surface_story`
- `misleading_assumptions`
- `forbidden_assumptions`

### 輸出

- `passed`
- `severity`
- `target_node`
- `issues`
- `revision_instruction`

### 責任邊界

應做：

- 檢查一致性、可玩性、可判定性、主題忠實度。
- 指定最小修正節點。
- 給出可操作的 revision instruction。

不得做：

- 不得直接重寫題目。
- 不得創作新設定。
- 不得只說「請改善」而沒有具體方向。
- 不得 `passed=false` 但 `issues=[]`。

### 審核分類

#### 一致性

- surface story 的每個異常都能在 truth、required/supporting facts 找到根據。
- surface story 沒有新增 truth、required/supporting facts 沒有的線索。
- surface story 為 required facts 中的真正原因保留至少一個可觀察入口。
- required/supporting facts 都來自 truth。
- forbidden assumptions 沒有否定 topic、truth 或 surface story 的客觀事實。

#### 可玩性

- 核心異常是人物行為異常，或至少是明確可追問的反常結果。
- 不是純店務流程、物品擺放、庫存、清潔、陳列、垃圾分類。
- 玩家能透過是非問答逐步逼近答案。
- 正解可以一句話概括。

#### 可判定性

- truth 足以回答常見 yes/no/irrelevant 問題。
- required solution facts 覆蓋勝負判定必要因果。
- 題目不依賴冷門專業知識或任意猜測。

#### 主題忠實度

- 使用者明確指定的場景、物品、動作、結果有保留。
- 若 topic 只是短場景，補充內容不得蓋過場景本身。
- 若 topic 指定「報警」「沒有 13 樓」等結果，truth 必須直接解釋。

### Target Node 選擇

- `generate_core_truth`
  - 核心不可玩。
  - 主線是店務流程或物品狀態。
  - 使用秘密組織、任務暗號、超自然、專業流程。
  - 有多條核心因果鏈。

- `expand_truth`
  - core truth 合理，但 truth 新增第二主線或不必要設定。
  - truth 過長或過度戲劇化。
  - truth 與 core truth 不一致。

- `extract_solution_facts`
  - required facts 遺漏核心因果。
  - required/supporting facts 新增 truth 沒有的設定。
  - required facts 條數不符合設定。
  - required facts 包含過細 supporting facts，導致通關門檻過嚴。

- `write_surface_story`
  - 謎面格式不符。
  - 謎面洩漏原因。
  - 謎面新增 truth、required/supporting facts 沒有的線索。
  - 謎面只有情緒或氣氛，沒有客觀異常。
  - 謎面缺少 required cause 的可觀察入口。

- `generate_assumptions`
  - forbidden assumptions 條數不符。
  - forbidden assumptions 否定 topic 或 surface story 客觀事實。

- `finalize_puzzle`
  - 所有項目通過。

### Revision Instruction 要求

`revision_instruction` 必須包含：

- 失敗原因。
- 要保留什麼。
- 要移除或避免什麼。
- 修正後的目標形態。

範例：

```text
核心真相目前只是商品陳列問題，不具備人物行為異常。請保留便利商店場景，改成某位顧客或店員做出看似不合理的行動，原因必須是日常可理解的誤會、證明或求助，不得使用秘密組織或店務流程作為解法。
```

## Deterministic Gate 對應

deterministic gate 不理解完整語意，只負責擋明顯違規。建議檢查分類應與 contract 對齊：

- `surface_story_too_long`
- `surface_story_too_short`
- `surface_story_sentence_count`
- `surface_story_explains_cause`
- `surface_story_contains_markup_or_comment`
- `surface_story_multiple_events`
- `truth_too_long`
- `truth_too_short`
- `required_solution_facts_count`
- `supporting_facts_count`
- `forbidden_assumptions_count`

語意型問題仍交給 reviewer：

- 核心不可玩。
- 店務流程主線。
- 秘密組織或任務暗號。
- 謎面新增未支持線索。
- truth 新增第二主線。

## Prompt Testing 對應

後續 prompt testing 應依 contract 評分，而不是只看 structured output 或 deterministic gate。

### 模型基準

目前 prompt contract 驗收應以 `qwen3.6-35b-a3b` 作為主要生成模型基準：

- runtime：llama.cpp OpenAI-compatible API。
- timeout：完整 pipeline 建議至少 `600` 秒。
- `max_tokens`：不預設限制，避免 reasoning 消耗 token 後截斷 JSON content。
- 驗收重點：是否產生可玩的核心因果與可判定 required solution facts，而不是單次生成速度。

`gemma4:e4b` 的測試結果仍可作為模型能力下限參考，但不再用來否定 prompt contract 的方向；若使用該模型，需搭配更強的 deterministic fallback 或 core-level reviewer。

### 節點級測試

- `generate_core_truth`
  - 測 `abnormal_result` 是否為人物行為異常。
  - 測是否避免店務流程、秘密組織、專業制度。

- `expand_truth`
  - 測是否保留 core truth。
  - 測是否新增第二主線。
  - 測 truth 字數是否穩定。

- `write_surface_story`
  - 測 2 句、50 到 120 字。
  - 測是否只使用 truth、required/supporting facts 已有內容。
  - 測是否只留下單一可見異常。
  - 測是否為真正原因留下公平線索。

- `extract_solution_facts`
  - 測 required facts 是否只包含通關最低必要事實。
  - 測 supporting facts 是否未被錯放成通關硬門檻。

- `review_puzzle`
  - 測能否打掉一致但不好玩的題目。
  - 測 target_node 是否準確。
  - 測 revision_instruction 是否可操作。

### Regression Topics

第二輪後續測試至少保留：

- `便利商店`
- `當兵期間操課`
- `電梯停在 13 樓，但大樓沒有 13 樓`
- `一名男子每天買同一款便當，直到店員報警`
- `學校舊教室、關掉的燈、還在轉的風扇`

### 驗收標準

一組 prompt 可進入正式實作，至少應滿足：

- `便利商店` 5 次中至少 4 次成功建立題目。
- 所有成功題目不得以店務流程、商品擺放、清潔、庫存作為主線。
- 所有成功題目的 surface story 都是 2 句、50 到 120 字、單一可見異常。
- reviewer 不得出現 `passed=false` 且 `issues=[]`。
- 平均 revision count 不超過 1。

## 後續實作順序

1. 依本 contract 調整正式 prompt。
2. 補強 deterministic gate 的分類名稱與 logging。
3. 補強 reviewer prompt，使其能檢查可玩性而不只是一致性。
4. 更新 `tools/pipeline_prompt_lab.py`，讓測試結果可直接對應 contract 欄位。
5. 跑 regression topics。
6. 若仍不穩，再考慮拆出獨立 `review_core_truth` 或 `playability_gate` 節點。
