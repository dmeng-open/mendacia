# Mendacia
A daily AI murder-mystery game where suspects lie to protect their secrets, but every case is proven by a solver to have exactly one solution. Python 3.12 (FastAPI, LangGraph, PydanticAI, clingo, LiteLLM), PostgreSQL + pgvector, React + TypeScript (Vite), Docker Compose.

## Commands
- `make ci` runs lint, typecheck, unit tests, and e2e tests (ruff, mypy, pytest, eslint, tsc, Playwright; e2e from Phase 3 on)
- `make up` starts PostgreSQL, the backend, and the frontend
- `make doctor` checks env vars, the database, and one cheap model call
- `make seed` loads the 3 hand-written cases from `cases/`
- `make check-case CASE=cases/<name>.json` runs the solver checks and prints any counterexample
- `make play-cli CASE=...` plays in the terminal; `make play` opens the browser game
- `make case` / `make cases N=10` generates and verifies new cases
- `make eval N=100` runs simulated playtests and writes the quality report (real model calls, capped by `EVAL_MAX_USD`)

## Docs
- `docs/spec.md`: what to build. `docs/plan.md`: phases, tasks, and acceptance criteria.
- `docs/adr/`: one record per design decision. `docs/QUESTIONS.md`: open questions for the human.

## Rules for agents
- Use poteto-mode for anything that touches more than one file.
- Never push to main, never merge a pull request, never deploy to production.
- Open pull requests ready for review, then stop.
- Every change ships with evidence: a test, a screenshot, or command output.
- Ask the human only for product or preference decisions.
- Work one phase of `docs/plan.md` at a time; do not start the next phase until every acceptance check passes.
- `make ci` and unit tests never call real models: replay recorded responses. Tests that call models are marked `live` and run only when explicitly enabled.
- Never hard-code model names; use `MODEL_FAST`, `MODEL_STRONG`, `MODEL_EMBED`. Every model call goes through the LiteLLM wrapper so tokens, cost, and latency are logged.
- Never commit `.env`.
- Suspects may lie only with the case's `planned_lies`. Never weaken the solver checks or the verifier to make a test pass.
- Changing the `Case` schema after Phase 1 means updating the hand-written cases, the solver, and the tests in the same PR, plus an ADR.
- If a rule can't be expressed in ASP, a run may exceed `EVAL_MAX_USD`, or an acceptance criterion looks wrong, write it to `docs/QUESTIONS.md` and stop.