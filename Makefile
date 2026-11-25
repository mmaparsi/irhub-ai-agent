.PHONY: up down logs test lint migrate

up:
	@test -f .env || cp .env.example .env
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

test:
	cd backend && python -m pytest -q

lint:
	cd backend && ruff check . && ruff format --check .
	cd frontend && npm run lint

migrate:
	cd backend && alembic upgrade head
