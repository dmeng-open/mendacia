#!/bin/bash
if [ "$CLAUDE_CODE_REMOTE" != "true" ]; then exit 0; fi
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null; then
  pip install --quiet uv
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

NODE_VERSION="$(cat frontend/.nvmrc)"
NODE_DIR="/opt/node-v${NODE_VERSION}"
if [ "$(node -v 2>/dev/null)" != "v${NODE_VERSION}" ] && [ ! -x "$NODE_DIR/bin/node" ]; then
  case "$(uname -m)" in
    x86_64) arch=x64 ;;
    aarch64 | arm64) arch=arm64 ;;
    *) echo "no Node build for $(uname -m)" >&2; exit 1 ;;
  esac
  tarball="node-v${NODE_VERSION}-linux-${arch}.tar.xz"
  tmp="$(mktemp -d)"
  curl -fsSL -o "$tmp/$tarball" "https://nodejs.org/dist/v${NODE_VERSION}/${tarball}"
  curl -fsSL -o "$tmp/SHASUMS256.txt" "https://nodejs.org/dist/v${NODE_VERSION}/SHASUMS256.txt"
  (cd "$tmp" && grep " ${tarball}\$" SHASUMS256.txt | sha256sum -c -)
  mkdir -p "$tmp/node"
  tar -xJf "$tmp/$tarball" -C "$tmp/node" --strip-components=1
  mv "$tmp/node" "$NODE_DIR"
  rm -rf "$tmp"
fi
if [ -x "$NODE_DIR/bin/node" ]; then export PATH="$NODE_DIR/bin:$PATH"; fi
(cd frontend && npm ci)
