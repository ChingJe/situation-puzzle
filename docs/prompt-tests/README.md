# Prompt 測試紀錄

此資料夾保存 `docs/plans/prompt-testing-plan.md` 相關的本地測試輸出。測試資料依輪次整理；正式設計結論請優先看各輪 `summary.md`，raw JSON 主要用於追查模型輸入、輸出與耗時。

## 目錄

- `round1-single-prompt/`：早期單次 `generate_puzzle`、`answer_question`、`judge_solution` prompt 測試。主要結論是單次題目生成不穩定，且問答有效性不適合完全交給 LLM。
- `round2-pipeline-v2/`：多節點 pipeline v2 與 contract prompt 測試。主要結論是拆節點能改善格式與一致性，但核心真相與可玩性仍需要更明確 contract。
- `round4-objective-claim/`：針對客觀敘述、謎面公平線索、`required_solution_facts` 最小通關門檻的測試。這是目前最接近正式 prompt 調整依據的測試紀錄。

## 工具

這些工具只用於 prompt lab，不會直接修改正式後端 prompt。

```bash
uv run python tools/prompt_lab.py generate --versions generate_puzzle.v0 便利商店 雨夜
uv run python tools/pipeline_prompt_lab.py baseline 便利商店
uv run python tools/prompt_round4_lab.py all
```

工具預設輸出位置：

- `tools/prompt_lab.py` -> `round1-single-prompt/`
- `tools/pipeline_prompt_lab.py` -> `round2-pipeline-v2/`
- `tools/prompt_round4_lab.py` -> `round4-objective-claim/`

## 閱讀順序

1. `round4-objective-claim/summary.md`
2. `round2-pipeline-v2/summary.md`
3. `round2-pipeline-v2/contract-test-notes.md`
4. `round1-single-prompt/summary.md`

`raw/` 與 `*.jsonl` 保留完整模型紀錄；若只需要決策脈絡，不必逐一閱讀。
