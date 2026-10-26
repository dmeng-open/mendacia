ENV_FILE := $(if $(wildcard .env),.env,.env.example)
ENV_NAMES := $(shell sed -n 's/^\([A-Z_]*\)=.*/\1/p' $(ENV_FILE))
$(foreach v,$(ENV_NAMES),$(if $(filter environment,$(origin $(v))),,$(eval export $(v) := $(shell sed -n 's/^$(v)=//p' $(ENV_FILE)))))

.PHONY: setup up db-create migrate api test lint typecheck ci doctor validate-cases check-case case cases generation-report lint-evidence record-fixtures play-cli sim scan-instructions audit agent-inventory security-regress seed retrieval-eval record-retrieval node-check web play api-types frontend-lint frontend-typecheck frontend-test e2e e2e-backend

NODE_VERSION := $(shell cat frontend/.nvmrc)
NODE_DIR ?= /opt/node-v$(NODE_VERSION)
ifneq ($(wildcard $(NODE_DIR)/bin/node),)
export PATH := $(NODE_DIR)/bin:$(PATH)
endif
E2E_DATABASE_URL ?= $(DATABASE_URL)_e2e
PLAY_CASE = $(if $(CASE),$(basename $(notdir $(CASE))),manor)

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
	cd backend && uv run mypy agents app engine evals evidence migrations security sim tests

ci: lint typecheck scan-instructions agent-inventory lint-evidence test security-regress frontend-lint frontend-typecheck frontend-test e2e

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
	cd frontend && npm audit --omit=dev --audit-level=high && npm audit signatures

doctor:
	cd backend && uv run python -m app.doctor $(if $(SKIP_MODEL),--skip-model)

validate-cases:
	PYTHONPATH=backend uv run --project backend python -m engine.cli validate cases/*.json

check-case:
	PYTHONPATH=backend uv run --project backend python -m engine.cli check $(CASE)

N ?= 10

case:
	cd backend && uv run python -m engine.cli generate --n 1

cases:
	cd backend && uv run python -m engine.cli generate --n $(N)

CONCURRENCY ?= 2

sim:
	cd backend && uv run python -m sim.runner --n $(N) --concurrency $(CONCURRENCY)

generation-report:
	cd backend && uv run python -m evals.generation_report

lint-evidence:
	PYTHONPATH=backend uv run --project backend python -m engine.cli lint-evidence cases/*.json

record-fixtures:
	cd backend && LLM_MODE=record uv run python -m tests.agents.record_suspect_fixtures $(SCENARIO)

play-cli:
	cd backend && uv run python -m app.cli --case $(abspath $(CASE))

seed:
	cd backend && LLM_MODE=$(if $(RECORD),record,replay) uv run python -W ignore::RuntimeWarning -m evidence.index ../cases/*.json

retrieval-eval:
	cd backend && LLM_MODE=$(if $(RECORD),record,replay) uv run python -m evals.retrieval

record-retrieval:
	$(MAKE) RECORD=1 seed retrieval-eval

node-check:
	@test "$$(node -v)" = "v$(NODE_VERSION)" || { echo "frontend/ needs Node $(NODE_VERSION) but found $$(node -v). Run scripts/install_pkgs.sh, or set NODE_DIR to a Node $(NODE_VERSION) install."; exit 1; }

web: node-check
	cd frontend && npx vite

play:
	@if ! curl -sf -o /dev/null localhost:$(API_PORT)/healthz; then \
		echo "starting the backend on $(API_PORT), log in $${TMPDIR:-/tmp}/mendacia-api.log"; \
		nohup $(MAKE) api > $${TMPDIR:-/tmp}/mendacia-api.log 2>&1 & \
	fi; \
	if ! curl -sf -o /dev/null localhost:$(WEB_PORT); then \
		echo "starting the frontend on $(WEB_PORT), log in $${TMPDIR:-/tmp}/mendacia-web.log"; \
		nohup $(MAKE) web > $${TMPDIR:-/tmp}/mendacia-web.log 2>&1 & \
	fi; \
	for _ in $$(seq 60); do curl -sf -o /dev/null localhost:$(WEB_PORT) && break; sleep 1; done; \
	url="http://localhost:$(WEB_PORT)/?case=$(PLAY_CASE)"; echo "$$url"; \
	(xdg-open "$$url" || open "$$url") > /dev/null 2>&1 || true

api-types: node-check
	cd backend && uv run python -c 'import json, sys; from app.main import app; json.dump(app.openapi(), sys.stdout)' > ../frontend/openapi.json
	cd frontend && npx openapi-typescript openapi.json -o src/api-types.ts; status=$$?; rm -f openapi.json; exit $$status

frontend-lint: node-check
	cd frontend && npx eslint . && npx prettier --check .

frontend-typecheck: node-check
	cd frontend && npx tsc --noEmit

frontend-test: node-check
	cd frontend && npx vitest run

e2e: node-check
	cd frontend && npx playwright test

e2e-backend:
	DATABASE_URL=$(E2E_DATABASE_URL) $(MAKE) db-create migrate seed
	cd backend && DATABASE_URL=$(E2E_DATABASE_URL) LLM_MODE=replay SESSION_SECRET=$(or $(SESSION_SECRET),e2e-session-secret) \
		uv run uvicorn app.main:app --port $(API_PORT)
