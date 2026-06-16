.PHONY: dev-backend dev-frontend test-backend check-frontend

dev-backend:
	uv run fastapi dev backend/app/main.py --host 0.0.0.0

dev-frontend:
	cd frontend && npm run dev

test-backend:
	uv run pytest

check-frontend:
	cd frontend && npm run build
