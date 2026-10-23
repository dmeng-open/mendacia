# Frontend

The Mendacia browser game: React 19 and TypeScript on Vite. ADR 017 explains the stack and the dependency rules.

## Run it

You need Node 24.21.0 (`frontend/.nvmrc`). `bash scripts/install_pkgs.sh` installs it and runs `npm ci`.

From the repository root:

```sh
make api       # backend on API_PORT (8000); needs SESSION_SECRET and a seeded database
make web       # Vite dev server on WEB_PORT (5173), proxying /games and /healthz to the backend
make play CASE=gallery   # starts whatever is not running and opens http://localhost:5173/?case=gallery
```

`make up` runs the database, the backend, and this app in Docker Compose instead.

## Check it

```sh
make frontend-lint frontend-typecheck frontend-test   # eslint and prettier, tsc, vitest
make e2e                                              # Playwright against a replay-mode backend
make api-types                                        # regenerate src/api-types.ts after a backend API change
```

`make e2e` starts its own replay backend on a `<DATABASE_URL>_e2e` database and serves the production build with `vite preview`. The browser driver for manual and live verification is described in `.claude/skills/verify/SKILL.md`.

## Rules

- Only `src/api.ts` talks to the wire. Components import types and verbs from `@/api`; ESLint enforces this.
- Install with exact versions only. `.npmrc` refuses versions younger than 14 days and never runs install scripts.
