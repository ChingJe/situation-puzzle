# Issue: 題目生成缺乏可解的具體真相

## 背景

2026-06-16 以真實 Ollama 模型 `gemma4:e4b` 測試一局遊戲，玩家主題只輸入「便利商店」。後端流程成功建立遊戲，但產生的題目本身缺乏明確目標與結論，導致玩家難以透過是非題推理。

相關 log：

- `logs/messages.log`
- `logs/app.log`
- request id: `req_6bae6491333a469ca8c43f1c5d28a6aa`
- game id: `7c9d4f10-6522-4f3c-8bee-c4175fce87b3`
- llm call id: `llm_af5619b2706b4371a503a2ba612098fd`

## 觀察結果

LLM 有成功回傳符合目前 schema 的 `PuzzleDraft`，包含：

- `title`
- `surface_story`
- `truth`
- `key_facts`
- `difficulty`

後端、LangGraph、structured output、Ollama 連線與 API response 流程都正常。問題主要集中在題目內容品質。

2026-06-16 後續測試加入 raw message log 後，又觀察到兩類更具體的品質問題：

- 主題「便利商店」生成的謎面同時包含「零食組合箱不見」與「快遞員喊電梯門票沒付錢」兩個異常，但真相將兩者拆成多個後勤流程，玩家自然追問兩者關係時被回答「無關」，造成遊戲主線不清。
- 主題「當兵期間操課」生成的謎面寫成「人體骨骼結構被移除」，但真相又說角色只是誤以為看到骨質碎片；玩家問「是否被其他人移除」時回答「否」，等於真相否定了謎面描述。

這些案例顯示：只靠單次 prompt 自檢不足以保證謎面、真相與 key facts 一致。

## 問題

### 1. 真相不是可解的答案

產生的 `truth` 偏向氛圍散文與主題評論，例如「日常與監控」、「城市生活中的微型生態系統」、「值得注意的規律和不尋常的細節」。它沒有明確交代：

- 到底發生了什麼事件。
- 誰做了什麼。
- 警報聲為什麼響。
- 玩家最終應該提交什麼具體解答。
- 謎面中的異常和真相之間的因果關係。

這會讓遊戲沒有穩定的解題目標。

### 2. 關鍵事實不是判定勝負用的核心事實

`key_facts` 目前被模型寫成主題描述或氣氛摘要，例如便利商店代表即時性、零食與宵夜構成日常慾望核心。這些內容不能用來可靠回答玩家問題，也不能作為 `judge_solution` 的判定依據。

理想上，`key_facts` 應該是玩家必須猜中的核心事實，例如：

- 角色身分或隱藏動機。
- 事件真正原因。
- 謎面誤導點。
- 造成異常結果的關鍵行動。
- 玩家提交解答時必須涵蓋的因果鏈。

### 3. 謎面長度限制沒有被程式強制執行

config 與 prompt 設定 `surface_story_max_chars = 150`，但這局 `app.log` 記錄：

```text
surface_story_length: 247
```

目前只有 prompt 要求模型遵守字數，`PuzzleDraft.surface_story` 沒有使用 Pydantic `max_length` 或後處理驗證，因此模型超出限制仍會被接受。

### 4. 生成 prompt 對「海龜湯可玩性」約束不足

目前生成 prompt 主要要求：

- 使用 zh-TW。
- 根據主題創作完整海龜湯。
- 謎面只提供異常事件。
- 真相 300 到 800 字。
- 關鍵事實 4 到 8 條。
- 避免不適合內容。

缺少以下硬性要求：

- 必須有唯一且具體的真相。
- 真相必須包含清楚的事件因果鏈。
- 謎面必須呈現一個明確矛盾或異常結果。
- `key_facts` 必須是解答判定用 facts，不得是主題評論。
- 不得輸出抽象主題總結、文學評論或氣氛分析。
- 玩家在不知道真相時，應能透過是非題逐步逼近答案。

### 5. 問答流程被低品質題目拖累

玩家提問「這些異常是純粹機械問題嗎?」時，模型回答 `no`。格式正確，但因為 `truth` 本身沒有具體機制，這個回答缺乏穩定推理價值。

也就是說，`answer_question` 節點本身沒有暴露明顯格式錯誤；真正問題是它依賴的 puzzle truth 不夠具體。

### 6. Dev reload log noise 影響觀察

`app.log` 中出現多筆 `watchfiles.main` 的 `changes detected`。這可能是 dev server reload 監看到 `logs/` 或 `data/` 寫入造成。它不是本 issue 的根因，但會讓觀察 log 時產生雜訊，也可能造成不必要的 reload。

## 影響

- 玩家看到的謎面像短篇場景，而不是可解謎題。
- 玩家無法判斷應該往哪個方向提問。
- AI 主持人的 yes/no/irrelevant 回答缺乏穩定真相基準。
- 解答提交時沒有明確標準答案可判斷。
- 歷史紀錄即使保存成功，也保存的是不可玩的題目。

## 目前結論

後續已將題目生成重構為多節點 pipeline，並針對 `interpret_topic`、`generate_core_truth`、`expand_truth`、`write_surface_story`、`review_puzzle` 定義 prompt contract。測試結果顯示：

- pipeline 與 prompt contract 能降低單次生成負擔，但無法完全彌補模型能力差距。
- `gemma4:e4b` 在短主題 `便利商店` 下仍容易生成店務流程、專業制度、抽象驗證或不可判定因果。
- `qwen3.6-35b-a3b` via llama.cpp OpenAI-compatible API 在相同 contract 方向下可生成合理題目：丈夫買水後只拿收據不拿商品，用來向妻子證明行蹤。
- 完整 pipeline 生成時間約 10 分鐘，目前視為可接受 tradeoff；題目品質、可玩性與可判定性優先於低延遲。

因此後續改善方向已從「只調整 prompt」改為：

- 支援 OpenAI-compatible provider。
- 將 `qwen3.6-35b-a3b` 作為主要題目生成模型基準。
- 提高 LLM request timeout。
- 保留 `gemma4:e4b` 作為輕量任務、fallback 或對照測試。
- 持續補強 deterministic gate、reviewer output validation 與短主題 fallback。

## 初步改善方向

後續實作時可考慮：

- 強化 `generate_puzzle` prompt，明確要求具體事件、因果鏈、唯一真相與可推理性。
- 在 prompt 中禁止抽象評論、主題分析與沒有結論的氛圍文字。
- 將 `key_facts` 定義為「玩家解答必須涵蓋的判定 facts」。
- 對 `surface_story` 加上 schema 或後處理長度驗證。
- 對 `truth`、`key_facts` 加入品質驗證或第二階段 critique/rewrite。
- 將題目生成拆成多階段：構思真相、產生謎面、品質檢查、必要時重寫。
- 將多階段生成正式化為 LangGraph pipeline：先產生核心真相，再擴寫 truth、抽取 key facts、最後撰寫 surface story。
- 加入能看見所有內容的 reviewer agent，檢查謎面是否把錯誤推論寫成客觀事實，以及每個異常是否都能被 truth 直接解釋。
- reviewer 不通過時依問題類型回到指定節點修正，而不是只整題重生。
- 排除 dev server 對 `logs/`、`data/` 的 reload 監看，降低 log noise。

重構設計見 `docs/design/puzzle-generation-pipeline.md`。

## 暫不處理

本文件只記錄問題與方向，尚未進行程式或 prompt 修改。
