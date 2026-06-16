# Prompt 測試紀錄

此資料夾保存 `docs/plans/prompt-testing-plan.md` 的本地測試輸出。

- `raw/`：每次 Ollama structured output 呼叫的 prompt、topic、輸出與耗時。
- `generation-runs.jsonl`：題目生成測試索引。
- `answer-runs.jsonl`：問答判定測試索引。
- `judge-runs.jsonl`：解答判定測試索引。
- `summary.md`：人工評分、比較結論與最終建議。

測試工具：

```bash
uv run python tools/prompt_lab.py generate --versions generate_puzzle.v0 便利商店 雨夜
```

此工具只用於 prompt lab，不修改正式後端 prompt。
