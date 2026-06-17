# 設計文件收斂

本文件是目前設計入口。若其他設計文件仍保留早期方案，以下列「目前採用」為準。

## 目前採用

- 遊戲型態：單人玩家對 AI 主持人。
- 題目來源：玩家輸入任意中文主題，AI 依主題產生完整海龜湯題目。
- 玩家可見資訊：遊戲進行中只顯示謎面與問答紀錄，不顯示真相與必要事實。
- 問答規則：玩家問題必須是是非題；主持人只回答「是／否／無關」。
- 勝利條件：玩家提交解答後，由 AI 判定是否命中必要解答事實。
- 失敗條件：無。玩家可無限提問。
- 後端：FastAPI + LangGraph/LangChain。
- 前端：React + Vite + TypeScript，透過 REST API 呼叫後端。
- 儲存：已結束遊戲以 JSON 存到本地 `data/games/`。
- 模型預設：llama.cpp OpenAI-compatible API，`qwen3.6-35b-a3b`。
- Ollama：保留支援，可作為 fallback provider。
- logging：保留 app log 與 raw message log，允許記錄 prompt、user request、agent/LLM raw response 與隱藏答案內容，供本機除錯。

## 題目生成主線

目前題目生成採多節點 pipeline，而不是單次生成：

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

設計重點：

- `generate_core_truth` 先固定一條可玩的核心因果鏈。
- `expand_truth` 只擴寫核心真相，不新增第二主線。
- `extract_solution_facts` 將通關必要事實與支撐事實分開。
- `write_surface_story` 最後才寫謎面，且必須提供能追問真正原因的公平線索。
- `review_puzzle` 可看見完整內容，負責一致性、可玩性、謎面公平性與主題忠實度審核。
- reviewer 失敗時應打回指定節點，而不是一律整題重生。

## Prompt 與品質準則

目前 prompt 調整方向以這三份文件為主：

- `prompt-contract.md`：各 agent 的目的、輸入邊界、輸出要求與 revision routing。
- `puzzle-quality-contract.md`：`PuzzleV2`、`required_solution_facts`、`supporting_facts` 與可玩性 gate。
- `puzzle-generation-pipeline.md`：pipeline 架構、state 與節點責任。

重要收斂：

- 題目核心應是「人物行為異常」或明確可追問的反常結果，不應只是商品擺放、清潔、補貨、標籤、庫存或場景混亂。
- 正解不能只是「正常流程」「看錯」「單純誤會」。
- 謎面不能洩漏關鍵行動、完整手法、動機或完整原因。
- 謎面必須為真正原因留下可觀察入口，例如痕跡、位置變化、時間關聯、物件狀態、異常聲音或旁人反應。
- 若 truth 有水管破裂，謎面不必直接寫「水管破裂」，但應有水痕、潮濕、天花板、滴水或相關表面現象。

## 其他設計文件用途

- `architecture.md`：整體專案分層與模組關係。
- `api-design.md`：REST API contract。
- `config.md`：`.env` 與 `config.toml` 責任分界。
- `data-model.md`：主要資料模型與儲存格式。
- `frontend-design.md`：前端畫面與互動設計。
- `game-flow.md`：遊戲流程與狀態轉換。
- `logging-design.md`：log 分層、raw message、request id 與隱私取捨。
- `testing-strategy.md`：測試範圍與驗收方式。

## 已過時但保留的內容

早期單次 `generate_puzzle` prompt、`key_facts` 作為唯一通關門檻、以及以 `gemma4:e4b` 作為主要題目生成模型的假設，現在都視為歷史紀錄。若在舊摘要或測試資料中看到這些方案，應以目前 pipeline + `PuzzleV2` contract 為準。
