# Situation Puzzle

單人海龜湯遊戲專案。玩家輸入主題後，由 Ollama 模型生成謎面與隱藏真相；玩家透過是非題提問，最後提交解答。

## 開發命令

後端：

```bash
uv run fastapi dev backend/app/main.py
```

前端：

```bash
cd frontend
npm run dev
```

也可以使用 Makefile：

```bash
make dev-backend
make dev-frontend
```

