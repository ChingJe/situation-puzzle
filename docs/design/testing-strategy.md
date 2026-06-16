# 測試策略

## 目標

第一版測試重點是確保後端狀態轉移、資料驗證、JSON 儲存與 LLM 包裝層可預期。前端先以編譯檢查為主。

## 後端測試

使用 `pytest`。

建議測試範圍：

- Pydantic schema validation。
- API request/response model。
- 統一錯誤格式。
- storage 寫入與讀取 JSON。
- 歷史列表摘要生成。
- 遊戲狀態轉移。
- 已結束遊戲不能繼續提問。
- 無效問題回傳 `INVALID_QUESTION`。
- 解答未解開時固定回「尚未解開」。
- 放棄後寫入 JSON。

## LLM 測試

測試不直接呼叫本機 Ollama，不依賴指定的本機模型。

使用 fake LLM 或 stub 固定輸出：

- 題目生成成功。
- 題目生成 structured output 第一次失敗、retry 後成功。
- 題目生成 retry 後仍失敗，回傳 `LLM_OUTPUT_INVALID`。
- 問題判定成功。
- 問題判定無效，回傳 `INVALID_QUESTION`。
- 解答判定成功與失敗。

## Storage 測試

使用 pytest temporary directory，不寫入真實 `data/games`。

建議案例：

- 寫入 solved 遊戲。
- 寫入 abandoned 遊戲。
- 讀取歷史詳情。
- 歷史列表依結束時間排序。
- JSON 檔案損壞時回傳或記錄 storage error。

## 前端檢查

第一版只做：

- TypeScript type check。
- production build。

不加入：

- Vitest
- Playwright
- 端到端測試

後續核心流程穩定後，再加入 Playwright 測：

- 建立遊戲。
- 提問。
- 無效問題錯誤。
- 提交未解開。
- 放棄顯示真相。
- 歷史紀錄顯示。

## 建議命令

後端：

```bash
uv run pytest
```

前端：

```bash
npm run build
```

Makefile 可提供：

```bash
make test-backend
make check-frontend
```
