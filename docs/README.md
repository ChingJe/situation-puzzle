# 文件總覽

本資料夾保存專案設計、計畫、問題紀錄與 prompt 測試資料。

## 目錄

- `design/`：目前有效的系統設計與 contract。新實作應優先參考 `design/README.md`。
- `plans/`：分階段開發與測試計畫。計畫可隨實作與測試結果調整。
- `issue/`：從實測與 log 分析整理出的問題紀錄。
- `prompt-tests/`：本地 prompt lab 的測試輸出、摘要與 raw response。

## 目前狀態

目前題目生成已從單次 `generate_puzzle` 收斂到多節點 pipeline，並以 llama.cpp OpenAI-compatible provider 的 `qwen3.6-35b-a3b` 作為預設生成模型。`gemma4:e4b` 保留為 Ollama fallback 或較輕任務的候選，但不作為題目生成品質基準。

後續若文件彼此衝突，優先順序為：

1. `design/README.md`
2. `design/prompt-contract.md`
3. `design/puzzle-quality-contract.md`
4. `design/puzzle-generation-pipeline.md`
5. `plans/development-plan.md`
6. 歷史 issue 與 prompt test 摘要
