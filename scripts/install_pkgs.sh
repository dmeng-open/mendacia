#!/bin/bash
if [ "$CLAUDE_CODE_REMOTE" != "true" ]; then exit 0; fi
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null; then
  pip install --quiet uv || curl -LsSf https://astral.sh/uv/install.sh | sh
fi

if ! command -v psql >/dev/null; then
  apt-get install -y -qq postgresql || { apt-get update -qq && apt-get install -y -qq postgresql; }
fi
PG_MAJOR="$(psql --version | sed -E 's/^[^0-9]*([0-9]+).*/\1/')"
if ! dpkg -s "postgresql-${PG_MAJOR}-pgvector" >/dev/null 2>&1; then
  apt-get install -y -qq "postgresql-${PG_MAJOR}-pgvector" \
    || { apt-get update -qq && apt-get install -y -qq "postgresql-${PG_MAJOR}-pgvector"; }
fi

service postgresql start || true
until pg_isready -q; do sleep 1; done

as_postgres() { runuser -u postgres -- psql -v ON_ERROR_STOP=1 -tA "$@"; }
if [ "$(as_postgres -c "select 1 from pg_roles where rolname = 'mendacia'")" != 1 ]; then
  as_postgres -c "create role mendacia login superuser password 'mendacia'"
fi
if [ "$(as_postgres -c "select 1 from pg_database where datname = 'mendacia'")" != 1 ]; then
  as_postgres -c "create database mendacia owner mendacia"
fi

(cd backend && uv sync --frozen)
if [ -f frontend/package-lock.json ]; then (cd frontend && npm ci); fi
