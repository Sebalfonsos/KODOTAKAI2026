.PHONY: up down migrate seed dev test eval lint fmt openapi load
up:        ; docker compose up -d --wait
down:      ; docker compose down
migrate:   ; uv run alembic upgrade head
seed:      ; uv run python -m app.seed
dev:       ; uv run uvicorn app.main:app --host 127.0.0.1 --port 8100 --reload
test:      ; uv run pytest -q -m "not eval" --cov=app --cov-report=term-missing:skip-covered
eval:      ; uv run pytest -q -m eval tests/eval
lint:      ; uv run ruff check . && uv run ruff format --check .
fmt:       ; uv run ruff format . && uv run ruff check --fix .
openapi:   ; uv run python -m app.openapi
load:      ; uv run python tests/load.py
