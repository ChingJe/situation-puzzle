# 資料模型

## Enum

### Game Status

```text
playing
solved
abandoned
```

### Answer

```text
yes
no
irrelevant
```

前端顯示對應：

```text
yes -> 是
no -> 否
irrelevant -> 無關
```

### Difficulty

```text
easy
medium
hard
```

第一版不提供難度選項，但 AI 生成題目時仍保存此欄位。

## 題目資料

正式題目資料仍維持單一 `Puzzle` 結構。這是進行中遊戲、問答判定、解答判定與結束後 JSON 儲存使用的資料。

目前實作仍使用下列 v1 結構。下一版題目品質設計會將 `key_facts` 拆分為 `required_solution_facts` 與 `supporting_facts`，並新增 `core_mystery`、`core_truth` 與 `quality_notes` 等內部欄位。詳細 schema 與遷移策略見 `docs/design/puzzle-quality-contract.md`。

```json
{
  "title": "雨夜發票",
  "surface_story": "某個雨夜，一名男子在便利商店撿到一張發票。隔天，他再也沒有回家。",
  "truth": "完整真相...",
  "key_facts": [
    "關鍵事實一",
    "關鍵事實二",
    "關鍵事實三",
    "關鍵事實四"
  ],
  "forbidden_assumptions": [
    "不應被誤判為真的假設"
  ],
  "difficulty": "medium"
}
```

## 題目生成中間資料

題目生成 pipeline 會使用多個中間 draft schema，但這些資料不進入 API response，也不保存到正式歷史 JSON。

建議 schema：

- `TopicInterpretation`：主題解析結果，包含場景、物件、角色、動作、明確結果與硬限制。
- `CoreTruthDraft`：一句話核心真相與結構化因果欄位。
- `TruthDraft`：擴寫後完整真相。
- `SolutionFactsDraft`：從真相抽出的通關必要事實與支撐事實。
- `SurfaceStoryDraft`：玩家可見謎面與標題。
- `AssumptionsDraft`：題目誤導方向與客觀上不成立的常見誤判。
- `PuzzleReviewResult`：reviewer 審核結果與修正目標。

只有通過 deterministic gate 與 reviewer 後，才會組成正式 `Puzzle`。

`PuzzleReviewResult` 範例：

```json
{
  "passed": false,
  "severity": "major",
  "target_node": "write_surface_story",
  "issues": [
    "謎面把錯誤推論寫成客觀事實"
  ],
  "revision_instruction": "保留 truth，只重寫謎面為單一客觀異常。"
}
```

## 問答紀錄

```json
{
  "question": "男子死亡了嗎？",
  "answer": "yes",
  "display_answer": "是",
  "created_at": "2026-06-16T11:00:00+08:00"
}
```

## 解答嘗試

```json
{
  "solution": "玩家提交的解答",
  "solved": false,
  "created_at": "2026-06-16T11:10:00+08:00"
}
```

未解開時前端只顯示「尚未解開」，不顯示 key facts 差異。

## 結束後遊戲紀錄

遊戲結束後保存為 `data/games/{game_id}.json`。

```json
{
  "game_id": "01JZ...",
  "topic": "雨夜、便利商店、一張沒有人認領的發票",
  "title": "雨夜發票",
  "surface_story": "某個雨夜，一名男子在便利商店撿到一張發票。隔天，他再也沒有回家。",
  "truth": "完整真相...",
  "key_facts": [
    "關鍵事實一",
    "關鍵事實二",
    "關鍵事實三",
    "關鍵事實四"
  ],
  "forbidden_assumptions": [
    "不應被誤判為真的假設"
  ],
  "difficulty": "medium",
  "questions": [
    {
      "question": "男子死亡了嗎？",
      "answer": "yes",
      "display_answer": "是",
      "created_at": "2026-06-16T11:00:00+08:00"
    }
  ],
  "solution_attempts": [
    {
      "solution": "玩家提交的解答",
      "solved": true,
      "created_at": "2026-06-16T11:20:00+08:00"
    }
  ],
  "status": "solved",
  "created_at": "2026-06-16T11:00:00+08:00",
  "ended_at": "2026-06-16T11:20:00+08:00"
}
```

## API 可見資料

遊戲進行中 API 不可回傳：

- `truth`
- `key_facts`
- `forbidden_assumptions`

遊戲結束後可以回傳：

- `truth`
- 完整問答紀錄
- 解答嘗試紀錄
- 結束狀態

## ID 與時間

- `game_id` 建議使用 ULID 或 UUID。
- 時間使用 ISO 8601 字串。
- 本地開發可使用系統時區，但 response 中應包含 offset，例如 `+08:00`。
