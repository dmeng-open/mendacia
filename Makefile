ENV_FILE := $(if $(wildcard .env),.env,.env.example)
ENV_NAMES := $(shell sed -n 's/^\([A-Z_]*\)=.*/\1/p' $(ENV_FILE))
$(foreach v,$(ENV_NAMES),$(if $(filter environment,$(origin $(v))),,$(eval export $(v) := $(shell sed -n 's/^$(v)=//p' $(ENV_FILE)))))

.PHONY: setup up db-create migrate api test lint typecheck ci doctor validate-cases check-case lint-evidence record-fixtures play-cli scan-instructions audit agent-inventory security-regress

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
	cd backend && uv run mypy agents app engine evals migrations security tests

ci: lint typecheck scan-instructions agent-inventory lint-evidence test security-regress

agent-inventory:
	cd backend && uv run python -m agents.inventory

security-regress:
	cd backend && LLM_MODE=$(if $(RECORD),record,replay) uv run python -m evals.security_regress

scan-instructions:
	python3 scripts/scan_instructions.py

audit:
	cd backend && uv export --frozen --no-emit-project --format requirements-txt > .audit-requirements.txt \
		&& uv run pip-audit --strict --require-hashes --disable-pip -r .audit-requirements.txt; \
		status=$$?; rm -f .audit-requirements.txt; exit $$status
	if [ -f frontend/package-lock.json ]; then cd frontend && npm audit --omit=dev --audit-level=high; fi

doctor:
	cd backend && uv run python -m app.doctor $(if $(SKIP_MODEL),--skip-model)

validate-cases:
	PYTHONPATH=backend uv run --project backend python -m engine.cli validate cases/*.json

check-case:
	PYTHONPATH=backend uv run --project backend python -m engine.cli check $(CASE)

lint-evidence:
	PYTHONPATH=backend uv run --project backend python -m engine.cli lint-evidence cases/*.json

record-fixtures:
	cd backend && LLM_MODE=record uv run python -m tests.agents.record_suspect_fixtures $(SCENARIO)

play-cli:
	cd backend && uv run python -m app.cli --case $(abspath $(CASE))
