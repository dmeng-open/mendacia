# Mendacia

A daily AI murder-mystery game where suspects lie to protect their secrets, but every case is proven by a solver to have exactly one solution. See `docs/plan.md` for the build plan and `CLAUDE.md` for project rules.

## Local commands

Copy `.env.example` to `.env` and fill in model keys when a phase needs them.

```
make setup            # install backend dependencies with uv
make up               # start PostgreSQL and the backend with Docker Compose
make db-create migrate  # create the database and run migrations
make api              # run the backend on API_PORT (default 8000)
make test             # run the backend tests
make ci               # ruff, mypy, and pytest
```

Check the backend with `curl -s localhost:8000/healthz`, which prints `{"status":"ok","db":"ok"}`.
