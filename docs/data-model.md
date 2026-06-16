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

