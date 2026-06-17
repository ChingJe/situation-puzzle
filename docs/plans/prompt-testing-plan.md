# Prompt 測試長任務計畫

## 目標

在不立刻修改正式遊戲流程的前提下，使用本機 LLM runtime 逐步測試與迭代 prompt，最終得到一組穩定可用的 prompt，讓 AI 能產生具備明確真相、可推理謎面、可判定 key facts 的海龜湯題目，並能支撐後續問答與解答判定流程。

可用 runtime 包含 Ollama API 與 llama.cpp OpenAI-compatible API。測試結論若涉及 provider 行為，需回饋到正式後端 provider adapter 設計，而不是只保留在 prompt lab 工具中。

此計畫回應 `docs/issue/puzzle-generation-quality.md` 中記錄的問題：目前 `generate_puzzle` 可能產生抽象氛圍文字，而不是可玩的海龜湯題目。

## 非目標

- 本階段不直接改正式 prompt。
- 本階段不直接改前端 UI。
- 本階段不追求大量自動化壓測。
- 本階段允許比較不同本地模型，並以題目品質決定主要生成模型。
- 本階段不要求每個主題都產生高文學品質故事，優先確保可玩性與可判定性。

## 測試前置條件

- 使用者在 Windows 端啟動目標 LLM runtime。
- WSL 端可透過 Windows gateway IP 呼叫 runtime API。
- 測試 Ollama 時，`.env` 中 `OLLAMA_BASE_URL` 指向可用的 Ollama endpoint，且 `.env` 中 `OLLAMA_MODEL=gemma4:e4b`，除非測試中明確比較其他模型。
- 測試 llama.cpp 時，Windows 端需啟動 OpenAI-compatible API，例如 `http://<windows-gateway-ip>:18080/v1`，且 `/v1/models` 可看到目標模型。
- `qwen3.6-35b-a3b` 目前作為主要生成模型候選；完整 pipeline timeout 建議至少 `600` 秒。
- 後端與前端可依 README 啟動，但 prompt 原型測試可先用直接呼叫 runtime API 或後端 LLM client 的方式進行。
- `logs/messages.log` 保持開啟 raw message logging，以便保存 prompt、raw response 與 parsed output。

## 主要產出

最終應產出：

- 一組穩定的 `generate_puzzle` prompt。
- 一組穩定的 `answer_question` prompt。
- 一組穩定的 `judge_solution` prompt。
- 題目生成品質標準。
- 測試案例與結果摘要。
- 如有需要，提出 schema/config 調整建議，但不在本計畫中直接要求實作。

第二輪 prompt testing 應在已完成的題目生成 pipeline 架構下產出：

- 一組穩定的 pipeline 節點 prompt：
  - `interpret_topic`
  - `generate_core_truth`
  - `expand_truth`
  - `extract_key_facts`
  - `write_surface_story`
  - `generate_forbidden_assumptions`
  - `review_puzzle`
- `write_surface_story` 專用 prompt 與 reviewer feedback 格式。
- deterministic gate 與 reviewer issue 的分類表。
- 多節點 retry 後仍失敗時的調整建議。
- 針對短主題「便利商店」等高風險題目的 regression cases。

## 測試原則

- 每輪只調整少量 prompt 變因，避免無法歸因。
- 優先測試短主題，因為短主題最容易暴露模型自行發散問題。
- 每次測試保留原始輸入、prompt 版本、模型輸出、人工評分與結論。
- 評估重點是「是否能玩」，不是文字是否漂亮。
- 若模型產生無具體答案的題目，該輪應視為失敗，即使 JSON 格式正確。

## 品質評分標準

每個生成題目以 0 到 2 分評估下列項目：

### 1. 真相具體性

- 0：真相是抽象評論或氛圍描述。
- 1：有事件輪廓，但缺少明確因果或關鍵行動。
- 2：清楚交代角色、行動、原因、結果與誤導點。

### 2. 謎面可推理性

- 0：只是場景描述，沒有明確異常或矛盾。
- 1：有異常，但線索不足或方向太散。
- 2：有明確異常結果，玩家可透過是非題逐步逼近真相。

### 3. Key Facts 可判定性

- 0：key facts 是主題評論或氣氛摘要。
- 1：部分 facts 可判定，但仍混入描述性文字。
- 2：每條 fact 都是解答判定需要的核心事實。

### 4. 問答穩定性

- 0：根據 truth 無法可靠回答 yes/no/irrelevant。
- 1：多數問題可回答，但部分關鍵問題含糊。
- 2：常見推理問題皆能根據 truth 穩定回答。

### 5. 解答判定穩定性

- 0：沒有明確標準答案。
- 1：大致可判定，但容易過寬或過嚴。
- 2：玩家解答只要涵蓋核心 facts 即可穩定判定 solved。

單題滿分 10 分。初步通過門檻為單題至少 8 分，且「真相具體性」、「Key Facts 可判定性」不得低於 2 分。

## 測試主題集

### 短主題

短主題用於測試模型自行補完故事的能力。

- 便利商店
- 雨夜
- 電梯
- 醫院
- 生日蛋糕
- 失蹤的鑰匙
- 半夜的電話
- 空白發票

### 中等主題

中等主題提供部分場景與元素。

- 雨夜、便利商店、一張沒有人認領的發票
- 學校舊教室、關掉的燈、還在轉的風扇
- 電梯停在 13 樓，但大樓沒有 13 樓
- 一名男子每天買同一款便當，直到店員報警

### 具限制主題

具限制主題用於測試 prompt 是否能遵守安全與玩法限制。

- 不要血腥，主題是深夜便利商店
- 不要死亡，主題是消失的生日禮物
- 主題是醫院，但不能需要醫學專業知識
- 主題是法律文件，但不能需要法律專業知識

## Prompt 測試階段

### 階段 1：建立 baseline

目的：

確認目前正式 prompt 的實際失敗型態。

步驟：

1. 使用目前正式 `generate_puzzle` prompt。
2. 對短主題集至少測 5 題。
3. 保存每題 raw output。
4. 依品質評分標準人工評分。
5. 彙整常見失敗模式。

預期輸出：

- baseline 評分表。
- 失敗模式列表。
- 是否重現 `便利商店` 題目品質問題。

### 階段 2：重寫題目生成 prompt

目的：

建立更明確的 `generate_puzzle` prompt，強制模型先設計可解真相，再輸出謎面。

測試方向：

- 明確定義海龜湯題目必須包含「表面異常」與「隱藏真相」。
- 要求 truth 必須包含角色、事件、原因、結果、誤導點。
- 要求 key facts 必須是玩家解答需要命中的核心 facts。
- 禁止抽象評論、主題分析、氣氛總結。
- 要求 surface story 只描述玩家可見事件，不解釋原因。
- 要求故事有唯一主要解答，不可開放式或象徵式。

預期輸出：

- `generate_puzzle` prompt candidate A。
- 測試結果與評分。
- 仍失敗的案例與原因。

### 階段 3：加入自我檢查規則

目的：

降低模型產生散文式或不可解題目的機率。

測試方向：

- 在 prompt 中要求模型輸出前自行檢查：
  - 是否有具體事件真相。
  - 是否能由 yes/no 問答推理。
  - key facts 是否都是具體事實。
  - surface story 是否超過字數。
- 若檢查不通過，要求模型重寫後再輸出最終 JSON。

注意：

自我檢查內容不一定要出現在最終 schema 中。若 schema 不包含 checklist，prompt 應要求模型在內部完成檢查，只輸出指定 JSON。

預期輸出：

- `generate_puzzle` prompt candidate B。
- 與 candidate A 的比較。

### 階段 4：測試 answer_question prompt

目的：

確認當題目品質改善後，主持人能根據 truth 與 key facts 穩定回答問題。

測試方法：

1. 選出 3 題高分生成題。
2. 為每題人工設計 10 個玩家問題：
   - 4 個應回答 yes。
   - 4 個應回答 no。
   - 2 個應回答 irrelevant。
3. 測試模型輸出是否符合預期。
4. 觀察是否需要調整 `answer_question` prompt。

重點：

- 主持人不能補充說明。
- 主持人不能提供提示。
- 若問題不是是非題，必須判定 invalid。
- 若問題語意可回答但措辭含糊，應盡量以 truth 為基準判斷。

預期輸出：

- `answer_question` prompt candidate。
- 問答準確率紀錄。

### 階段 5：測試 judge_solution prompt

目的：

確認玩家提交解答時，模型能根據核心 facts 判定 solved。

測試方法：

1. 選出 3 題高分生成題。
2. 為每題人工設計 6 個解答：
   - 2 個完整正解。
   - 2 個部分命中但缺關鍵因果。
   - 2 個錯誤解答。
3. 測試 `judge_solution` 是否只在完整正解時回傳 solved。

重點：

- 不要求逐字相同。
- 必須涵蓋主要因果與關鍵轉折。
- 不應因玩家猜到氣氛或主題就判定成功。

預期輸出：

- `judge_solution` prompt candidate。
- 解答判定準確率紀錄。

### 階段 6：完整遊戲流程人工測試

目的：

確認 prompt 組合在實際遊戲中能支撐順暢流程。

測試方法：

1. 使用候選 prompt 組合啟動後端。
2. 開啟前端。
3. 從短主題、中等主題、具限制主題各選至少 1 題。
4. 每題完成：
   - 建立遊戲。
   - 玩家只看謎面。
   - 問至少 8 個是非題。
   - 提交錯誤解答。
   - 提交正確解答或放棄。
   - 確認歷史紀錄可讀。

預期輸出：

- 至少 3 局完整測試紀錄。
- 每局是否可玩。
- 每局遇到的 prompt 問題。

### 階段 7：穩定性驗收

目的：

確認 prompt 不是只對少數案例有效。

驗收標準：

- 至少測試 12 個不同主題。
- 生成題目平均分數至少 8 分。
- 真相具體性低於 2 分的題目不超過 1 題。
- Key Facts 可判定性低於 2 分的題目不超過 1 題。
- 問答測試準確率至少 85%。
- 解答判定測試準確率至少 85%。
- 至少 3 局完整前端流程可順利完成。

## 第二輪：Pipeline 架構 Prompt 測試

### 背景

第一輪 prompt testing 後，正式題目生成已從單一 `generate_puzzle` 改為多節點 pipeline：

```text
interpret_topic
  -> generate_core_truth
  -> expand_truth
  -> extract_key_facts
  -> write_surface_story
  -> generate_forbidden_assumptions
  -> review_puzzle
  -> finalize_puzzle
```

目前新架構已能阻擋不合格題目，但實測 `便利商店` 仍暴露新的失敗型態：

- `write_surface_story` 會把完整真相摘要寫進謎面。
- 謎面過長，常超過 `strict_surface_story_max_chars`。
- 謎面包含原因、行動者、結果、情緒反應等多個事件段落。
- deterministic gate 會反覆要求重寫，但模型收到「太長／多異常」後仍未收斂到短謎面。
- revision 用盡後後端回 `LLM_OUTPUT_INVALID`，題目建立失敗。

因此第二輪測試不再只測「能否產生一題完整 JSON」，而是要確認每個 pipeline 節點都能穩定完成自己的單一責任，尤其是謎面撰寫與 reviewer feedback 是否能形成有效修正閉環。

### 第二輪目標

- 讓 `write_surface_story` 穩定輸出 2 句、50 到 120 字、只含單一可見異常的謎面。
- 讓 `review_puzzle` 的 `revision_instruction` 足夠具體，可引導指定節點成功修正。
- 降低同一節點重試後仍違反 deterministic gate 的比例。
- 確認短主題不會被模型補成完整日常故事摘要。
- 保留 pipeline 拆分帶來的一致性優勢，不回退到單次生成。

### 第二輪非目標

- 不調整前端。
- 不改變玩家可見 API contract。
- 不以提高 `max_revision_rounds` 作為主要解法。
- 不放寬謎面品質標準來讓題目勉強通過。
- 不要求模型產生文學化或驚悚化文字，優先追求可玩與可判定。

### 第二輪測試資料

第二輪應保留第一輪主題集，並新增下列 regression cases：

- `便利商店`
  - 重現 request `req_70f78d7cd13a45ecadf2e825582fee21` 的失敗型態。
  - 期待謎面只留下「顧客根據可見資訊做出期待，結果與期待衝突」。
- `當兵期間操課`
  - 防止謎面把角色誤認寫成客觀事實。
  - 期待謎面若涉及誤會，必須使用「他以為／他看到」。
- `學校舊教室、關掉的燈、還在轉的風扇`
  - 測試是否會引入特殊系統或超自然。
- `電梯停在 13 樓，但大樓沒有 13 樓`
  - 測試 topic explicit result 必須被保留且解釋。
- `一名男子每天買同一款便當，直到店員報警`
  - 測試主題明確結果「報警」不可被弱化。

### 節點級測試階段

#### 階段 A：重放正式失敗案例

目的：

建立新架構 baseline，確認問題是否可重現，並記錄每個節點的 raw input/output。

步驟：

1. 使用目前正式 pipeline prompt。
2. 針對 `便利商店` 跑至少 3 次。
3. 保留每次完整 raw message log。
4. 標記失敗發生在哪個節點：
   - deterministic gate
   - reviewer
   - structured output
   - revision exhausted
5. 特別紀錄 `write_surface_story` 的字數、句數、是否洩漏原因、是否多異常。

驗收輸出：

- baseline run 表。
- 失敗樣本庫。
- `write_surface_story` 主要違規分類。

#### 階段 B：單獨測試 `write_surface_story`

目的：

在固定 `truth` 與 `key_facts` 的條件下，只測謎面 prompt，避免其他節點干擾。

測試方法：

1. 從 baseline 選出 5 組 `truth + key_facts`。
2. 對每組套用不同 `write_surface_story` prompt candidate。
3. 每個 candidate 至少跑 3 次，觀察穩定性。
4. 使用 deterministic gate 自動標記：
   - 長度是否 50 到 120 字。
   - 是否剛好 2 句。
   - 是否含「因為／其實／原來／真相」等解釋詞。
   - 是否包含原因、行動者的關鍵行動、完整結論。
   - 是否包含兩個以上主要事件。

候選 prompt 方向：

- `write_surface_story.v1`：強化「只寫結果，不寫原因」。
- `write_surface_story.v2`：要求先在內部選出唯一可見異常，再只輸出該異常。
- `write_surface_story.v3`：加入反例，例如「不要寫店員誤貼標籤；要寫顧客明明照標籤買，結果反應不如預期」。
- `write_surface_story.v4`：限制輸出句型，例如：
  - 第一句：角色看到或做了一件普通行為。
  - 第二句：出現與期待相反的結果。

通過門檻：

- 5 組測資中至少 4 組可一次通過 deterministic gate。
- 同一組測資連跑 3 次，至少 2 次合格。
- 不得洩漏造成異常的真正原因。

#### 階段 C：測試 reviewer feedback 是否可修正

目的：

確認 `review_puzzle` 不是只指出失敗，而是能產生可操作的修正指令。

測試方法：

1. 人工準備 5 個不合格 `surface_story`。
2. 讓 `review_puzzle` 判定 `target_node` 與 `revision_instruction`。
3. 將 `revision_instruction` 送回 `write_surface_story`。
4. 檢查重寫後是否通過 deterministic gate。

reviewer feedback 應避免：

- 只說「謎面太長」。
- 只說「請更簡潔」。
- 未指出應刪除原因、流程或多餘事件。

reviewer feedback 應包含：

- 要保留的單一可見異常。
- 要刪除的內容類型，例如原因、行動者、完整流程、心理判斷。
- 字數與句數要求。
- 是否必須改成「他以為／他看到」避免客觀事實錯誤。

通過門檻：

- reviewer 的 `target_node` 準確率至少 80%。
- 收到 reviewer feedback 後，`write_surface_story` 修正成功率至少 70%。

#### 階段 D：測試 deterministic gate 與 prompt 的協作

目的：

確認 gate 不是只阻擋，而能提供足夠細分的失敗理由讓 prompt revision 成功。

測試方向：

- 將 gate issue 從籠統描述拆成可被 prompt 使用的分類：
  - `surface_story_too_long`
  - `surface_story_too_many_sentences`
  - `surface_story_explains_cause`
  - `surface_story_multiple_events`
  - `surface_story_denies_truth`
  - `surface_story_subjective_inference_as_fact`
- 測試每種 issue 對應的 revision instruction template。
- 觀察是否需要讓 gate 在 state 中保存 `failed_checks`，而不只保存自然語言 issues。

通過門檻：

- 每種 gate issue 至少有 1 個測試樣本。
- 對 `write_surface_story` 的 gate issue，二次修正後成功率至少 80%。

#### 階段 E：完整 pipeline 測試

目的：

確認節點級 prompt 調整放回完整 pipeline 後仍可穩定運作。

測試方法：

1. 使用候選 prompt 組合跑完整 pipeline。
2. 每個主題至少跑 1 次，短主題 `便利商店` 至少跑 5 次。
3. 記錄：
   - 總耗時。
   - LLM call 次數。
   - revision 次數。
   - 最終是否成功建立題目。
   - 題目品質分數。
4. 對成功題目接續測 `answer_question` 與 `judge_solution`。

通過門檻：

- `便利商店` 5 次中至少 4 次成功建立題目。
- 全測試集成功率至少 85%。
- 平均 revision 次數不超過 1。
- 成功題目中，謎面可推理性平均至少 1.7/2。
- 不得再出現謎面把 truth 否定的內容寫成客觀事實。

### 第二輪紀錄格式

第二輪除原本紀錄欄位外，應新增：

```text
pipeline prompt set：
node：
node prompt version：
deterministic gate result：
failed_checks：
review_target_node：
review_issues：
revision_instruction：
revision_count：
surface_story_chars：
surface_story_sentence_count：
surface_story_leaks_cause：
surface_story_multiple_events：
surface_story_objective_fact_conflict：
final_pipeline_status：
```

### 第二輪完成定義

第二輪 prompt testing 完成時，應具備：

- 一組可提交實作的 pipeline prompt set。
- `write_surface_story` 的穩定 prompt 與反例規則。
- reviewer feedback 的格式與範本。
- deterministic gate issue 分類與是否需要程式調整的建議。
- 至少一份 regression report，證明 `便利商店` 不再因謎面過長或多異常而 revision exhausted。

## 第三輪：模型能力與 Provider 測試結論

第二輪 contract prompt testing 顯示，`gemma4:e4b` 在短主題題目生成上仍難以穩定遵守 contract。主要失敗型態包括：

- 將 `便利商店` 補成商品批次、過敏原、檢測等專業流程。
- 使用身份/狀態驗證、保密事務等抽象且不可判定原因。
- 產生不自然或因果不清的核心真相。
- reviewer revision instruction 偶爾為空，導致修正空轉。

追加測試 `qwen3.6-35b-a3b` via llama.cpp OpenAI-compatible API 後，使用相同 contract 方向可產生合格題目：

- 主題：`便利商店`
- 結果：`ok`
- target：`finalize_puzzle`
- deterministic gate：通過
- reviewer：通過
- 生成時間：約 605 秒
- 題目核心：丈夫買水後只拿收據不拿商品，用來向妻子證明行蹤。

目前決策：

- 接受約 10 分鐘開局生成時間作為合理 tradeoff。
- 主要生成模型與後續正式預設改以 `qwen3.6-35b-a3b` 為基準。
- `gemma4:e4b` 保留為輕量任務、fallback 或對照測試，不再作為題目生成品質主要基準。
- OpenAI-compatible provider 已納入正式後端；後續 prompt testing 可直接透過正式 app 或 prompt lab 對照驗證。

### 第三輪後續驗收方式

由於 Qwen 單次完整 pipeline 較慢，驗收批次應重品質、少量但具代表性：

1. `便利商店` 先跑 3 次，至少 2 次人工判讀通過。
2. Regression topics 各跑 1 次：
   - `當兵期間操課`
   - `電梯停在 13 樓，但大樓沒有 13 樓`
   - `一名男子每天買同一款便當，直到店員報警`
   - `學校舊教室、關掉的燈、還在轉的風扇`
3. 每筆成功題目至少人工檢查：
   - core truth 是否是一條具體日常因果鏈。
   - surface story 是否只含玩家可見異常。
   - key facts 是否足以判定正解。
   - reviewer 是否未漏判明顯不可玩題目。

Qwen 測試中不應設定過低 `max_tokens`。若 llama.cpp 回傳包含 `reasoning_content`，解析時應只使用 `message.content` 作為 JSON 內容來源。

這項結論應回饋到 `docs/plans/development-plan.md` 的正式 provider adapter 階段：

- `.env` 需要 `LLM_PROVIDER=openai-compatible`、`OPENAI_COMPATIBLE_BASE_URL`、`OPENAI_COMPATIBLE_MODEL`。
- `config.toml` 需要 `openai_compatible_max_tokens = 0` 或足夠高的可調設定。
- `request_timeout_seconds` 需要足以涵蓋 Qwen 長生成，建議至少 600 秒。
- 正式後端 health、logging、raw message log 都應使用通用 LLM provider 欄位，而不是寫死 Ollama。

## 第四輪：Puzzle V2 後的謎面客觀性與解答事實測試

### 背景

導入 `PuzzleV2`、`required_solution_facts`、`supporting_facts` 與低可玩性 gate 後，實測 `便利商店` 題目已不再退化成「正常補貨」這類直覺日常流程。`game_id=69a91ea9-1bc4-482c-ba71-3e3eb70e1cea` 顯示新結構可以支撐完整遊戲：

- 題目成功建立，`schema_version=2`。
- 玩家透過問答逐步確認自動門、物體感應與商品被人帶走。
- 玩家提交「有人用店內物品卡住自動門，躲開監視器把限定商品偷走」後判定 `solved=true`。

但本局仍暴露新的 prompt 問題：

- `surface_story` 使用「全程無人靠近」這種絕對客觀描述，但 truth 中實際有人走向後方貨架拿走商品。
- 「不翼而飛」與「全程無人」等詞若未限定為角色視角，容易讓謎面和真相衝突。
- 題目可玩但偏向偷竊手法推理，海龜湯反轉感仍偏弱。
- `required_solution_facts` 仍可能包含玩家自然解答不一定需要完整說出的誤導校正。

第四輪測試目標是微調 prompt 與 reviewer contract，不再重構資料結構。

### 第四輪目標

- 讓 `write_surface_story` 避免未被 truth 支持的絕對客觀措辭。
- 讓 reviewer 明確檢查謎面的每個強斷言是否由 truth 支持。
- 讓 `extract_solution_facts` 更穩定區分 required 與 supporting facts。
- 保持 v2 schema 與目前 pipeline，不新增新節點。
- 保持 `judge_solution` 可接受玩家自然短解答，不要求復述完整 truth。

### 第四輪非目標

- 不更換主要生成模型。
- 不修改前端。
- 不再重設 puzzle schema。
- 不用提高 `max_revision_rounds` 解決品質問題。
- 不把所有犯罪或偷竊題材全面禁止，但要避免題目只剩手法推理。

### Regression Case

#### Case A：便利商店自動門

來源：

- `game_id=69a91ea9-1bc4-482c-ba71-3e3eb70e1cea`
- topic：`便利商店`

本局可接受之處：

- 核心真相有具體行動與關鍵物件。
- 問答流程能逐步縮小範圍。
- 解答判定合理。

本局需改善之處：

- 謎面：

```text
便利商店的自動門反覆開合，限定商品卻不翼而飛，全程無人靠近。監視器拍下空門晃動的畫面後，店內眾人皆以為是幽靈作祟。
```

問題：

- 「全程無人靠近」被寫成客觀事實，但 truth 需要有人接近貨架並拿走商品。
- 「限定商品卻不翼而飛」若不是角色主觀感受，也容易暗示客觀不可解事件。

可接受改寫方向：

```text
便利商店的自動門反覆開合，限定商品也在店員沒注意時消失了。監視器畫面看起來只有空門晃動，店內眾人因此以為是幽靈作祟。
```

或：

```text
便利商店的自動門反覆開合，店員回頭時發現限定商品已經不見。監視器畫面像是沒有人靠近貨架，店內眾人因此以為是幽靈作祟。
```

驗收重點：

- 可使用「看起來」「以為」「店員回頭時發現」表示視角限制。
- 不可把「無人靠近」「無人碰過」「憑空消失」寫成 truth 未支持的客觀事實。

### Prompt Candidate 測試方向

#### `write_surface_story.v10-objective-guard`

新增規則：

- 若 truth 中有人、物或行動造成異常，謎面不得寫「全程無人」「完全沒有人」「沒有人靠近」「沒有人碰過」作為客觀事實。
- 若角色不知道原因，必須使用視角限定：
  - 「看起來」
  - 「他以為」
  - 「監視畫面像是」
  - 「店員回頭時發現」
  - 「眾人誤以為」
- 「不翼而飛」「憑空消失」只能作為角色感受，不得作為客觀敘述。
- 謎面應保留單一可見異常，不應同時描述完整手法。

測試方法：

1. 固定 `truth`、`required_solution_facts`、`supporting_facts`，只重跑 `write_surface_story`。
2. 至少使用 5 組 truth：
   - 便利商店自動門與限定商品。
   - 水族館少右眼的魚。
   - 電梯沒有 13 樓。
   - 學校舊教室風扇。
   - 每天買同一款便當直到店員報警。
3. 每組跑 3 次。
4. 人工標記：
   - 是否有絕對客觀詞。
   - 是否用視角限定修正。
   - 是否洩漏手法。
   - 是否仍有明確可問的異常。

通過門檻：

- 15 次中至少 12 次無 unsupported absolute claim。
- 15 次中至少 12 次謎面仍可推理。
- 不得出現 truth 明確否定的謎面客觀事實。

#### `review_puzzle.v2-objective-claim-check`

新增審核規則：

- Reviewer 必須逐一檢查 surface story 中的強斷言。
- 下列詞若出現，必須確認 truth 是否客觀支持：
  - 全程無人
  - 完全沒有人
  - 沒有人靠近
  - 沒有人碰過
  - 憑空消失
  - 不翼而飛
  - 自己
  - 突然
- 若 truth 只是角色沒看見、監視器角度沒拍到、眾人誤以為，surface story 必須改成主觀視角描述。
- 若 surface story 的強斷言會讓玩家排除真相中的必要行動，必須 `passed=false` 且 `target_node=write_surface_story`。

測試方法：

1. 人工準備 8 個 surface story：
   - 4 個含 unsupported absolute claim。
   - 2 個使用正確視角限定。
   - 2 個一般合格謎面。
2. 讓 reviewer 判斷是否通過。
3. 對不通過樣本檢查 `target_node` 是否為 `write_surface_story`。
4. 對 revision instruction 檢查是否明確指出：
   - 哪個詞是 unsupported absolute claim。
   - 應改成何種視角限定。
   - 要保留哪個單一異常。

通過門檻：

- unsupported absolute claim 偵測率至少 90%。
- 合格謎面誤殺率不超過 20%。
- revision instruction 可被 `write_surface_story` 用於成功修正的比例至少 70%。

#### `extract_solution_facts.v2-minimum-required`

新增規則：

- `required_solution_facts` 只放玩家正解必須直接或等價命中的事實。
- 誤導校正若只是「眾人誤以為」或「看起來像」，通常放入 `supporting_facts`。
- required facts 建議 2 到 3 條；只有題目真的需要時才允許第 4 條。
- 每條 required fact 必須符合：「若玩家沒說這條，答案就真的不完整」。

測試方法：

1. 使用已完成或人工整理的 5 題 truth。
2. 對每題產出 solution facts。
3. 人工設計 3 種玩家解答：
   - 精簡自然正解。
   - 缺少真正原因的部分解。
   - 誤導方向錯誤解。
4. 檢查精簡自然正解是否能命中 required facts。

通過門檻：

- 每題 required facts 平均 2 到 3 條。
- 精簡自然正解通過率至少 90%。
- 部分解與錯解不應被 required facts 誤判為完整。

### Deterministic Gate 補充測試

第四輪以 prompt 為主，但應同時評估是否需要新增輕量 deterministic gate。

候選 gate：

```text
surface_story_unsupported_absolute_terms
```

候選詞：

- 全程無人
- 完全沒有人
- 沒有人靠近
- 沒有人碰過
- 憑空消失
- 不翼而飛

Gate 不應直接判定所有出現皆失敗，而是先作為 `warning` 類型記錄；若 prompt 測試顯示 reviewer 常漏判，再升級為 blocking gate。

測試紀錄欄位新增：

```text
surface_story_absolute_terms：
surface_story_has_viewpoint_qualifier：
surface_story_absolute_claim_supported_by_truth：
reviewer_detected_unsupported_absolute_claim：
required_fact_count：
natural_solution_should_pass：
natural_solution_matched_required_fact_ids：
```

### 第四輪完整驗收

測試批次：

1. `便利商店`：至少 3 次完整 pipeline。
2. `一條少了右眼的魚`：至少 1 次完整 pipeline。
3. `電梯停在 13 樓，但大樓沒有 13 樓`：至少 1 次完整 pipeline。
4. `學校舊教室、關掉的燈、還在轉的風扇`：至少 1 次完整 pipeline。
5. `一名男子每天買同一款便當，直到店員報警`：至少 1 次完整 pipeline。

通過門檻：

- 完整 pipeline 成功率至少 80%。
- 成功題目中 unsupported absolute claim 為 0。
- 成功題目中 required facts 平均不超過 3.5 條。
- 每題至少一個精簡自然正解可被 `judge_solution` 判為 solved。
- `便利商店` 題目不得回到正常補貨、打掃、盤點、陳列等低可玩流程。

### 第四輪完成定義

完成時應產出：

- `write_surface_story.v10-objective-guard` 是否採用的結論。
- `review_puzzle.v2-objective-claim-check` 是否採用的結論。
- `extract_solution_facts.v2-minimum-required` 是否採用的結論。
- 是否需要新增 deterministic gate 的決策。
- 至少一份 regression report，包含 `game_id=69a91ea9-1bc4-482c-ba71-3e3eb70e1cea` 對照修正前後差異。

## 測試紀錄格式

每輪測試建議記錄：

```text
日期：
模型：
prompt 版本：
主題：
生成結果摘要：
真相具體性：
謎面可推理性：
Key Facts 可判定性：
問答穩定性：
解答判定穩定性：
總分：
失敗原因：
下一輪調整：
相關 request_id / game_id / llm_call_id：
```

## Prompt 候選管理

建議每次候選 prompt 都標記版本：

- `generate_puzzle.v0`：目前正式版本。
- `generate_puzzle.v1`：強化具體真相與 key facts。
- `generate_puzzle.v2`：加入內部自我檢查。
- `answer_question.v1`：針對高品質 truth 的問答判定。
- `judge_solution.v1`：針對 key facts 的解答判定。

在正式改程式前，應先在測試紀錄中明確指出採用哪組版本。

## 可能需要的後續程式調整

Prompt 測試完成後，可能會建議另開實作任務處理：

- 對 `PuzzleDraft.surface_story` 加上 `max_length`。
- 對 `truth` 加上最小品質檢查或長度範圍驗證。
- 對 `key_facts` 加上每條最小長度與最大長度。
- 增加題目品質 critique/rewrite graph node。
- 排除 dev server reload 監看 `logs/` 與 `data/`。
- 新增 prompt regression 測試資料。

這些調整不屬於本文件的立即執行範圍。

## 完成定義

此長任務完成時，應具備：

- 一組通過驗收標準的 prompt。
- 清楚的測試紀錄與比較結果。
- 對正式程式需要調整的具體建議。
- 可支撐後續 implementation commit 的 prompt 內容與驗收依據。
