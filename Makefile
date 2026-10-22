ENV_FILE := $(if $(wildcard .env),.env,.env.example)
ENV_NAMES := $(shell sed -n 's/^\([A-Z_]*\)=.*/\1/p' $(ENV_FILE))
$(foreach v,$(ENV_NAMES),$(if $(filter environment,$(origin $(v))),,$(eval export $(v) := $(shell sed -n 's/^$(v)=//p' $(ENV_FILE)))))

.PHONY: setup up db-create migrate api test lint typecheck ci

setup:
	cd backend && uv sync --frozen

up:
	docker compose up --build

db-create:
	@admin="postgresql$${DATABASE_URL#postgresql+psycopg}"; \
	name="$${admin##*/}"; \
	psql "$${admin%/*}/postgres" -tAc "select 1 from pg_database where datname = '$$name'" | grep -q 1 \
		|| psql "$${admin%/*}/postgres" -c "create database \"$$name\""

migrate:
	cd backend && uv run alembic upgrade head

api:
	cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port $(API_PORT)

test: db-create
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .

typecheck:
	cd backend && uv run mypy

ci: lint typecheck test
