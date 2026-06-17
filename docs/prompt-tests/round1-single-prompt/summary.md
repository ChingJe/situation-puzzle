# Prompt 測試結果摘要

日期：2026-06-16  
模型：`gemma4:e4b`  
Ollama endpoint：`http://192.168.192.1:11434`  
主要測試工具：`tools/prompt_lab.py`  

## 結論

本輪測試確認：目前的 `gemma4:e4b` 可以透過 prompt 大幅改善海龜湯題目品質，但「只靠單次生成 prompt」尚未穩定達到 `docs/plans/prompt-testing-plan.md` 的完整驗收門檻。

建議採用的穩定方案不是單一 prompt，而是：

1. `generate_puzzle.v8` 作為下一輪正式生成 prompt 基礎。
2. 題目生成後加入 deterministic quality gate，不合格則 retry 或請模型重寫。
3. `answer_question` 改為程式先判斷是否為是非題，再讓 LLM 只判斷 `yes/no/irrelevant`。
4. `judge_solution.v2` 可作為正式解答判定 prompt 基礎。

## 主要發現

### 題目生成

`generate_puzzle.v0` 能產生 JSON，但常見問題嚴重：

- 真相是散文式背景、都市傳說或抽象設定。
- key facts 混入氣氛描述，不是可判定事實。
- surface story 經常超過設定長度。
- 題目沒有唯一可命中的結論。

逐步測試後：

- `v1/v2` 改善具體性，但仍偏長、偏陰謀或專業設定。
- `v4/v5` 將題目拉回日常型誤會，品質明顯提升。
- `v6/v7` 加強 key facts 與主題忠實度，但仍會忽略明確主題結果。
- `v8` 用獨立短 prompt 取代疊加式 prompt，對「便利商店」「空白發票」改善較好，但仍未完全解決「報警」「沒有 13 樓」這類強約束。

### 12 題 v7 生成測試

| 主題 | 評分 | 備註 |
| --- | ---: | --- |
| 便利商店 | 6 | 謎面語意不夠自然，truth 和監視器描述不完全貼合 |
| 雨夜 | 8 | 可玩，真相清楚 |
| 電梯 | 8 | 可玩，但偏設備操作 |
| 醫院 | 8 | 日常誤會清楚 |
| 生日蛋糕 | 7 | 主題保留，但「蛋糕架」描述不自然 |
| 失蹤的鑰匙 | 9 | 最穩定，可直接作為回歸案例 |
| 半夜的電話 | 8 | 真相具體，但情節稍偏惡意騷擾 |
| 空白發票 | 6 | 沒有真正處理「空白發票」核心 |
| 雨夜便利商店發票 | 7 | 可玩但流程稍複雜 |
| 舊教室風扇 | 8 | 可玩，key facts 清楚 |
| 13 樓電梯 | 7 | 可玩但仍使用偏系統化解釋 |
| 每天買便當直到報警 | 5 | 未保留「報警」這個明確結果 |

平均：約 7.25 / 10。未達 8 / 10 驗收門檻。

### v8 針對性測試

| 主題 | 結果 |
| --- | --- |
| 便利商店 | 改善，能形成普通日常異常 |
| 空白發票 | 改善，保留「空白發票」 |
| 13 樓電梯 | 仍使用「虛擬樓層／系統介面」解釋，不夠日常 |
| 每天買便當直到報警 | 仍弱化「報警」，改成類似嚴肅盤查 |

## 問答判定

測試 prompt：

- `answer_question.v1`
- `answer_question.v2`
- `answer_question.v3`
- `answer_question.v4`

最佳結果是 `answer_question.v3`，在 `失蹤的鑰匙` 題上約 8 / 10。

主要問題：

- 模型會把「答案是否定」的有效問題誤判為 invalid。
- 模型會把「可回答但無關」的問題誤判為 invalid。
- 模型偶爾輸出不一致欄位，例如 `is_valid_question=false` 但 `answer=irrelevant`。

結論：`answer_question` 不建議只靠 LLM prompt 判斷有效性。正式流程應改成：

1. 後端先用規則判定是否為是非題。
2. 非是非題直接回 `請輸入可用是／否回答的問題`。
3. 是非題才交給 LLM 判斷 `yes/no/irrelevant`。
4. LLM schema 最好移除 `is_valid_question`，或新增後處理保證欄位一致。

## 解答判定

`judge_solution.v1` 太寬鬆，會把部分命中判定為 solved。

`judge_solution.v2` 在三題共 18 個案例中達到 18 / 18：

- `失蹤的鑰匙`：6 / 6
- `醫院`：6 / 6
- `學校舊教室、關掉的燈、還在轉的風扇`：6 / 6

`judge_solution.v2` 可作為下一輪正式 prompt 基礎。

## 建議採用 Prompt

### generate_puzzle 基礎 prompt

建議以 `generate_puzzle.v8` 為基礎，但必須搭配 quality gate。

```text
你是海龜湯出題主持人。請產生一題短、明確、可用是／否問答解開的日常型海龜湯。
所有欄位必須使用 zh-TW，用繁體中文。

主題忠實度是最高優先：
- 玩家主題中的物品、場景、動作、結果都必須保留，不可替換成相近詞。
- 若主題包含明確結果，例如「報警」「空白發票」「沒有 13 樓」，surface_story 和 truth 都必須直接包含並解釋該結果。
- 不要弱化主題結果，例如不要把「報警」改成只是緊張或警惕。

故事限制：
- 一個場景、一個異常、一個真相；主要角色最多 2 人。
- 真相必須是普通生活誤會、時間差、視角誤判、物品被整理、標示被誤讀、或日常流程造成。
- 禁止大型陰謀、秘密組織、超自然、未知科技、複雜犯罪、醫療專業、法律專業。
- 除非主題明確提到，禁止使用系統升級、模擬模式、自動警報、駭客、特殊機制解釋。

欄位要求：
- surface_story：剛好 2 句，50 到 120 個中文字；只寫玩家看到的異常結果，不解釋原因。
- truth：200 到 340 個中文字；必須說明誰、因為什麼、做了什麼、造成什麼結果、玩家為何誤會。
- key_facts：4 到 5 條；必須完整覆蓋真正原因、關鍵行動者、關鍵行動、造成的結果、表面誤導點。
- forbidden_assumptions：2 到 3 條；只能列客觀上不成立的錯誤原因，不可否定主題指定的事實。
- difficulty：固定 medium。

輸出前自檢，不要輸出自檢文字：
- surface_story 的每個異常是否都能在 truth 和 key_facts 找到直接解釋？
- 正解是否能用一句話說完？
- 是否保留了玩家主題所有明確元素？
- 是否沒有引入不必要的系統、背景或配角？
```

### answer_question 建議 prompt

若仍維持現有 schema，可先使用 `answer_question.v3`，但不建議只靠它上線。

```text
你是海龜湯主持人。你只做兩步判定：先判斷問題形式是否有效，再判斷答案。

第一步：is_valid_question
- 問題如果是「嗎／是否／有沒有／是不是／會不會／能不能」這類可用是或否回答的事實問題，必須判定 true。
- 不可以因為答案是 no 而判 invalid。
- 不可以因為問題與真相無關而判 invalid；這種情況 answer 應為 irrelevant。
- 只有要求提示、要求解釋、要求直接說真相、開放式問題、主觀感想問題，才判 false。

第二步：answer
- 陳述依 truth 為真：yes。
- 陳述依 truth 為假或與 truth 衝突：no。
- 問題形式有效，但問的事實和解開核心真相無關：irrelevant。
- is_valid_question=false 時，answer 必須為 null。

不要補充說明，不要提示，不要洩漏未被問到的資訊。
```

正式實作建議改成後端規則先判定問題形式，LLM 只回 `answer`。

### judge_solution prompt

```text
你是海龜湯遊戲主持人，負責判定玩家提交的完整解答是否已解開謎題。
只回傳 solved 布林值，不提供提示或解釋。

solved=true 必須同時滿足：
- 玩家說出造成謎面異常的真正原因。
- 玩家說出關鍵行動者做了什麼。
- 玩家說出該行動如何導致謎面中的反常結果。
- 玩家說法沒有和 truth 或 key_facts 的核心事實衝突。

solved=false 的情況：
- 只猜到不是偷竊、不是超自然、只是誤會等排除性答案。
- 只猜到物品大概位置或角色大概關係，但缺少造成異常的關鍵行動。
- 缺少 key_facts 中任一個必要因果環節。
- 使用錯誤原因解釋，即使部分細節命中。

判定時以 key_facts 為最低必要門檻；玩家不必逐字相同，但必須完整覆蓋核心因果鏈。
```

## 後續實作建議

- 在 `PuzzleDraft` 加上欄位描述與約束，例如 `surface_story` max length、`truth` length、`key_facts` 每條長度。
- 新增生成後 quality gate：
  - 主題關鍵詞是否保留。
  - surface_story 是否過長。
  - key_facts 是否包含真正原因、行動者、行動、結果、誤導點。
  - forbidden_assumptions 是否否定了主題指定事實。
- quality gate 失敗時 retry，最多使用 config 中的 retry 次數。
- 將 `answer_question` 拆成 deterministic question-form validation + LLM answer classification。
- 將 `judge_solution.v2` 實作為正式 prompt。
