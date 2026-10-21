# Mendacia MVP plan

This plan builds the Mendacia MVP from an empty repo in 16 stacked PRs across 7 phases.
Players get a daily murder mystery in the terminal after Phase 2 and in the browser after Phase 3.
The program enforces one rule. No case reaches a player unless clingo proves it has exactly one culprit, and suspects lie only with the case's `planned_lies`.
Each PR runs in its own Claude Code cloud session on Linux. The operator lands every PR.
PR ids in order are P0-1, P0-2, P1-1, P1-2, P2-1, P2-2, P2-3, P3-1, P3-2, P3-3, P3-4, P4-1, P4-2, P5-1, P5-2, P6-1.
The feature spec is `docs/spec.md`. Project rules are in `CLAUDE.md`.

## How to read this

One box is one unit of work. Every box names the evidence that checks it. A nested box is a sub-step of the box above it. Check a box only when its evidence exists, a file, a log line, a screenshot, a test run, or a SHA. The body is a how-to. The appendices explain and record.

The program runs `skills/poteto-mode/playbooks/autopilot-stack.md` from the installed plugin. The work is sequenced phase by phase and `CLAUDE.md` withholds merge authority, so owners stop at STACK-READY and the operator lands every PR bottom-up. Every PR is the operator's item and stops at merge-ready. No agent pushes to `main`, merges a PR, or deploys.

Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

The operator set live verification to two lanes per PR. Each PR has Lane 1, the regression lane against trunk, and Lane 2, the load-bearing scenario the diff adds. This overrides the ten lanes in the bundled playbook.

## Program checklist

### Arm the program

- [ ] State the protocol and this plan to the operator, then stop. Start execution only on the operator's explicit go.
- [ ] Confirm the operator items below exist before the first owner starts. Each one is a decision or a credential only the operator holds.
  - [ ] `main` has a root commit with `CLAUDE.md`, `.claude/settings.json`, `scripts/install_pkgs.sh`, `docs/spec.md`, and this `docs/plan.md`. The operator pushes it, because `CLAUDE.md` forbids agents from pushing to `main`.
  - [ ] A Claude Code cloud environment named `mendacia` exists for the repo. Its secrets hold one provider key per model, `MODEL_FAST`, `MODEL_STRONG`, `MODEL_EMBED`, `EMBED_DIM`, and `EVAL_MAX_USD`. Its network allowlist reaches PyPI, npm, the Ubuntu apt mirrors, GitHub, and each model provider host.
  - [ ] The operator picks the embedding provider for `MODEL_EMBED`. Anthropic has no embedding model, so this needs a second provider key.
  - [ ] The repo has GitHub Actions secrets for the manual live-eval workflow in P5-2.
- [ ] On the operator's go, write this exact text into the standing orders and restate it in your todolist. "Plan `docs/plan.md`. PRs in order P0-1, P0-2, P1-1, P1-2, P2-1, P2-2, P2-3, P3-1, P3-2, P3-3, P3-4, P4-1, P4-2, P5-1, P5-2, P6-1. Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Live verification is two lanes per PR. Owners stop at STACK-READY. The operator lands every PR. A phase starts only after the operator lands the previous phase and finishes its checkpoint. Done when P6-1 is landed and its fresh-machine check passes."
- [ ] Read these from the installed plugin at program start. Re-read them at every tick.
  - [ ] `skills/poteto-mode/playbooks/autopilot-stack.md`
  - [ ] `skills/poteto-mode/playbooks/autopilot-full.md`
  - [ ] `skills/swarm/SKILL.md`
  - [ ] The driver skill. The `run` skill that ships with Claude Code drives the CLI and the backend. From P3-4 on, the project skill at `.claude/skills/verify/SKILL.md` drives the browser.
  - [ ] `skills/poteto-mode/playbooks/opening-a-pr.md`
  - [ ] `skills/architect/SKILL.md`, `skills/interrogate/SKILL.md`, `skills/tdd/SKILL.md`, and `skills/show-me-your-work/SKILL.md`
- [ ] Arm the hourly audit tick as a real `/loop` in dynamic mode, which schedules its own wake-up rather than blocking on a sleep. Never leave the cadence to memory.
- [ ] Use this tick prompt, verbatim. "Re-read the execution playbook from the installed plugin and the standing objective. Audit the operation against both and fix drift in this tick. Probe every active lane and judge progress by side effects only. Stand down a stuck lane and dispatch its replacement now. Then post a short status message to the operator in chat only when the audit found a tracked change that no earlier status message reported, such as a PR opened, a code-ready head, a round launched or closed, a verdict, a merge, a stuck agent and the action taken, a blocker added or cleared, or a decision only the operator can make. Name every such change and nothing else. Do not repeat a table, the merged list, or an unchanged blocker. If the audit found none, end the turn with no reply text. Either way, log this tick's row in your decision trail. The row names the items reported, or none."
- [ ] Judge cloud-session progress by side effects on GitHub only. Read branch heads, PR state, and check runs with `gh pr view <number> --json headRefOid,statusCheckRollup`.
- [ ] On the operator's hold or stand-down, send every owner a zero-writes order at once.

### Spawn owners

- [ ] Start one Claude Code cloud session per PR on the `mendacia` environment. Its brief is this plan's PR section, the standing orders, and the path of this plan. The session is that PR's owner for its full lifecycle under the execution playbook.
- [ ] Follow this dependency graph. Start dependent work only after its parent merges, or base it on the parent branch when the execution playbook stacks.
  - [ ] P0-1 is first. It branches from `main` as `phase-0/scaffold`.
  - [ ] P0-2 after P0-1. Then the Phase 0 gate.
  - [ ] P1-1 after the Phase 0 gate. P1-2 after P1-1. Then the Phase 1 checkpoint.
  - [ ] P2-1 after the Phase 1 checkpoint. P2-2 after P2-1. P2-3 after P2-2. Then the Phase 2 checkpoint.
  - [ ] P3-1 after the Phase 2 checkpoint. P3-2 after P3-1. P3-3 after P3-2. P3-4 after P3-3. Then the Phase 3 gate.
  - [ ] P4-1 after the Phase 3 gate. P4-2 after P4-1. Then the Phase 4 gate.
  - [ ] P5-1 after the Phase 4 gate. P5-2 after P5-1. Then the Phase 5 checkpoint.
  - [ ] P6-1 after the Phase 5 checkpoint.
- [ ] Hold the phase gates. A gate opens only when the operator has landed every PR of the phase and every acceptance command of that phase passes on `main`.
- [ ] Hold the operator checkpoints after Phase 1, Phase 2, and Phase 5. The operator reads the ASP encoding after Phase 1, the verifier rules after Phase 2, and the metric definitions after Phase 5. The next phase waits for the operator's go in chat.
- [ ] Hold the file boundaries.
  - [ ] Phase 0 PRs touch only repo tooling, `backend/app/`, `backend/migrations/`, `backend/tests/`, `docs/`, and `scripts/`.
  - [ ] Phase 1 PRs touch only `backend/engine/`, `backend/tests/engine/`, `cases/`, `docs/adr/`, and `Makefile`.
  - [ ] Phase 2 PRs touch only `backend/agents/`, `backend/app/`, `backend/migrations/`, `backend/tests/`, `docs/adr/`, and `Makefile`.
  - [ ] P3-1 touches only `cases/` and `backend/engine/cli.py`. Other Phase 3 PRs add `backend/evidence/`, `backend/evals/`, and `frontend/`.
  - [ ] Any PR that changes the `Case` schema after P1-1 updates the hand-written cases, the solver, the tests, and adds an ADR in the same PR.
- [ ] Hold the review gate. P2-3, P3-4, and P4-2 change an interaction. They wait for the operator's review in chat with screenshots and a video before merge.
- [ ] Hold the stop conditions. An owner writes the item to `docs/QUESTIONS.md`, pushes, reports it, and stops when a rule cannot be expressed in ASP, when a run may exceed `EVAL_MAX_USD`, when an acceptance criterion looks wrong, or when a core spec rule would need to change.

### PR mechanics, for every PR

- [ ] Resolve the forge once. Default to `gh`; if `command -v origin` succeeds and Origin can resolve the repository, use `origin pr` for every PR operation. Record any fallback to `gh`. Never require `gt`.
- [ ] Open the PR ready, never draft, per **Opening a PR**. Use the run's built-in PR tool when it has one, else `origin pr create --status open --base <base-branch>` or `gh pr create --base <base-branch>` according to the resolved forge. A stack child targets its parent branch.
- [ ] Name branches `phase-<n>/<slug>`. Each PR has its own branch, so one phase can span several stacked branches.
- [ ] List every acceptance command of the PR with its output in the PR description, per the operator's plan rules.
- [ ] Run `make lint typecheck` once before the PR-facing push. Push with hooks on.
- [ ] Run `/deslop` before each commit and `/no-comments` before review.
- [ ] Run the **architect** skill before code in P1-2, P2-1, P2-2, P3-2, and P4-1. Run the **interrogate** skill before code-ready in the same PRs.
- [ ] Triage every review-bot and security-reviewer comment per `../references/bugbot-triage.md`.
- [ ] Before the code-ready report and babysit, and again after merge prep, record the base and head SHAs prepared by the topology owner under the execution playbook.
- [ ] Keep `make ci` free of real model calls. Tests that call models carry `@pytest.mark.live` and run only with `pytest -m live`.

### Verdict and merge, for every PR

- [ ] A full swarm runs once, at the code-ready head. Another full swarm runs only for new behavior, a redesign, or a large new diff. A rebase, a merge-conflict resolution, or a minor fix gets a single verifier at the new head. Run each full swarm per `skills/swarm/SKILL.md`. One gates lane. The two live lanes from the PR's **Verify, live** block. The perf lane from its **Verify, perf** block. Two or more audit lanes, each with its own focus, that read the diff and the receipts and distrust the PR body. The root audits the receipts in the merge-ready report before the verdict.
- [ ] Run each verdict swarm in a fresh cloud session at the head SHA, not in the owner's session. The owner's own lane runs are receipts, not the verdict.
- [ ] Clean only when every lane is `PASS`. Findings go back to the owner, including a defect that a lane filed as a note. A new head gets a fresh verdict, except for results that stay valid under the patch-id rule in `playbooks/shipping.md`.
- [ ] Append each clean PR to the base-branch stack with its base set to its parent branch, per `playbooks/autopilot-stack.md` step 2. The operator lands the stack bottom-up. Apply the patch-id rule from `playbooks/shipping.md` to every verdict carried across a rebase.

### Boot recipe, for every live lane

Each live lane runs in its own worktree at the PR head. Drive through the skill path or exact commands recorded in this boot recipe.

- [ ] `git fetch origin <head-branch> && git checkout <head SHA>`. Run this in `git worktree add /tmp/lane-<n>` so each lane has its own tree.
- [ ] Run `bash scripts/install_pkgs.sh`. From P0-1 on it starts PostgreSQL, installs pgvector, runs `uv sync` in `backend/`, and runs `npm ci` in `frontend/` when a lockfile exists. It is safe to rerun.
- [ ] Give each lane its own database and ports, so lanes share no writable state. Export `DATABASE_URL=postgresql+psycopg://mendacia:mendacia@localhost/mendacia_lane_<n>`, `API_PORT=$((8000+n))`, and `WEB_PORT=$((5173+n))`. Run `make db-create migrate`.
- [ ] Start the backend with `make api`. Wait until `curl -sf localhost:$API_PORT/healthz` returns 200. From P3-4 on, start the frontend with `make web` and wait until `curl -sf localhost:$WEB_PORT` returns 200.
- [ ] Deliver input only through the driver skill's commands. The CLI and the backend go through the `run` skill. The browser goes through `.claude/skills/verify/SKILL.md` once P3-4 creates it, which runs Playwright. Read-only diagnostics are `psql "$DATABASE_URL" -c '<select>'` on `llm_calls`, `verifier_events`, and `generation_log`, and the backend log.
- [ ] Before a lane that calls real models, set `LLM_MODE=live` and `LANE_MAX_USD=1`. After the lane, sum `cost_usd` in `llm_calls`. The lane fails if the sum exceeds `LANE_MAX_USD`, except the eval lane in P5-2, which uses `EVAL_MAX_USD`.
- [ ] For a perf probe, run the probe at trunk, head, trunk, head, trunk, head and take the median of each side.
- [ ] Save every screenshot to `/tmp/swarm-<pr-id>/worker-<n>/<slug>.png` and return the paths with the report. A terminal lane saves its transcript as `<slug>.txt` beside the screenshots.

## Scaffold the repo, compose stack, and CI (P0-1)

**Depends on.** None.

**Files.**

- [ ] Create `backend/pyproject.toml` and `backend/uv.lock` with Python 3.12, FastAPI, SQLAlchemy async, psycopg, Alembic, pydantic-settings, pytest, ruff, and mypy in strict mode.
- [ ] Create `backend/app/main.py`, `backend/app/config.py`, and `backend/app/db.py`.
- [ ] Create `backend/alembic.ini`, `backend/migrations/env.py`, and `backend/migrations/versions/0001_enable_pgvector.py`.
- [ ] Create `backend/Dockerfile`, `docker-compose.yml`, `.env.example`, and `.gitignore`.
- [ ] Create `Makefile`.
- [ ] Create `frontend/README.md` as the frontend stub.
- [ ] Create `.github/workflows/ci.yml`.
- [ ] Create `docs/adr/000-record-architecture-decisions.md`, `docs/QUESTIONS.md`, and `README.md`.
- [ ] Edit `scripts/install_pkgs.sh`.
- [ ] Create `backend/tests/test_health.py`.

**Build.**

- [ ] Add `Settings` in `backend/app/config.py`. It loads `DATABASE_URL`, `MODEL_FAST`, `MODEL_STRONG`, `MODEL_EMBED`, `EMBED_DIM`, and `EVAL_MAX_USD` from the environment and `.env`. A missing variable fails at startup with its name.
- [ ] Add `GET /healthz` in `backend/app/main.py`. It returns `{"status":"ok","db":"ok"}` after `select 1`, and 503 with the database error when the query fails.
- [ ] Add migration `0001_enable_pgvector.py` with `create extension if not exists vector`.
- [ ] Add `docker-compose.yml` with `db` on the `pgvector/pgvector:pg16` image and `backend` running `uvicorn --reload` with `backend/` mounted.
- [ ] Add `Makefile` targets `setup`, `up`, `db-create`, `migrate`, `api`, `test`, `lint`, `typecheck`, and `ci`. `make ci` runs ruff, mypy, and pytest.
- [ ] Add `.github/workflows/ci.yml` with a `fast` job that runs `make ci` against a `pgvector/pgvector:pg16` service, and a `compose-smoke` job that runs `docker compose up -d --wait` and `curl -sf localhost:8000/healthz`.
- [ ] Make `scripts/install_pkgs.sh` idempotent for cloud sessions. It installs uv when missing, installs the pgvector package that matches the installed PostgreSQL major version, starts PostgreSQL, creates the `mendacia` role, runs `uv sync` in `backend/`, and runs `npm ci` in `frontend/` when `frontend/package-lock.json` exists.
- [ ] Probe the cloud session first and record the result in the PR description. Run `docker info`, `psql --version`, and `apt-cache policy postgresql-16-pgvector`. If Docker is missing, the lanes use native PostgreSQL and the `compose-smoke` CI job is the evidence for the compose path.
- [ ] Write `docs/QUESTIONS.md` with one heading per open item and `README.md` with the six local commands from `docs/spec.md`.

**You see.**

- [ ] `curl -s localhost:8000/healthz` prints `{"status":"ok","db":"ok"}`.
- [ ] `make ci` prints `All checks passed!` from ruff, `Success: no issues found` from mypy, and a pytest summary with 0 failed.
- [ ] The `fast` and `compose-smoke` checks are green on the PR.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `backend/tests/test_health.py` gains a case for 200 with a live database and a case for 503 with a bad `DATABASE_URL`. Run `make test`.
- [ ] `backend/tests/test_config.py` gains a case where a missing `MODEL_FAST` fails with that name. Run `make test`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Two lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run `bash scripts/install_pkgs.sh && make ci` in a fresh worktree at trunk and at head. Trunk has no backend, so record that trunk exits without installing anything, and gate the head bootstrap plus `make ci`. Save `bootstrap.txt`. Pass when the head bootstrap exits 0 twice in a row and `make ci` reports 0 failed.
- [ ] Lane 2. Start the backend with `make api`, curl `/healthz`, stop PostgreSQL with `service postgresql stop`, and curl again. Save `healthz.txt`. Pass when the first call returns 200 with `"db":"ok"` and the second returns 503 naming the connection error.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time of `make ci` and of a cold `bash scripts/install_pkgs.sh`. Trunk lacks both, so the diff-added work is the bootstrap and the end state the owner waits for is a green `make ci`.
- [ ] Probe. `/usr/bin/time -f %e make ci` and `/usr/bin/time -f %e bash scripts/install_pkgs.sh` in a fresh session, interleaved per the boot recipe.
- [ ] Baseline. Record the trunk `install_pkgs.sh` time first. Record `make ci` at trunk as absent.
- [ ] Rule. Fail when the head `make ci` median exceeds 90 s or the cold bootstrap exceeds 240 s.

**Review gate.** None. P0-1 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The root appends P0-1 to the base-branch stack and the operator lands it bottom-up.

## Route every model call through one recorded wrapper (P0-2)

**Depends on.** P0-1.

**Files.**

- [ ] Create `backend/app/llm.py`.
- [ ] Create `backend/app/llm_replay.py`.
- [ ] Create `backend/migrations/versions/0002_llm_calls.py`.
- [ ] Create `backend/app/doctor.py`.
- [ ] Create `backend/tests/conftest.py`, `backend/tests/test_llm.py`, and `backend/tests/test_llm_boundary.py`.
- [ ] Create `backend/tests/fixtures/llm/`.
- [ ] Create `docs/adr/003-llm-record-replay.md`.
- [ ] Edit `Makefile` and `.github/workflows/ci.yml`.

**Build.**

- [ ] Add `complete(role, messages, *, response_format=None, purpose, game_id=None)` and `embed(texts, *, purpose)` in `backend/app/llm.py`. `role` is `ModelRole.FAST`, `ModelRole.STRONG`, or `ModelRole.EMBED` and resolves to the configured model name. Each call writes one `llm_calls` row with model, role, purpose, game id, prompt tokens, completion tokens, `cost_usd` from LiteLLM's cost table, and `latency_ms`.
- [ ] Add `LLM_MODE` with values `live`, `record`, and `replay` in `backend/app/llm_replay.py`. Replay keys each call by a SHA-256 of role, messages, and parameters, reads `backend/tests/fixtures/llm/<key>.json`, and raises `MissingRecording` naming the key when no file exists. Replay still writes the `llm_calls` row from the recorded usage.
- [ ] Set `LLM_MODE=replay` in `backend/tests/conftest.py` for every test not marked `live`. Register the `live` marker and add `-m "not live"` to pytest `addopts`.
- [ ] Add `backend/tests/test_llm_boundary.py`. It fails when any module other than `app/llm.py` imports `litellm`, and when any source file outside `.env.example` contains a model name literal matching `gpt-|claude-|gemini-|text-embedding-`. The failure message names the file and says to call `app.llm`.
- [ ] Add `make doctor`. It checks every `Settings` variable, runs `select 1`, and makes one `complete(ModelRole.FAST, ...)` call with `max_tokens=1`. It prints one `OK` or `FAIL` line per check and exits non-zero on any failure. `make doctor SKIP_MODEL=1` skips the model call for CI.
- [ ] Write `docs/adr/003-llm-record-replay.md` with the key scheme and why replay lives in the wrapper.

**You see.**

- [ ] `make doctor` prints `OK env`, `OK db`, and `OK model <MODEL_FAST> <tokens> tokens <cost> USD <ms> ms`.
- [ ] `psql "$DATABASE_URL" -c 'select model, purpose, cost_usd, latency_ms from llm_calls'` shows the doctor call.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `backend/tests/test_llm.py` gains a replay hit that writes one `llm_calls` row, a replay miss that raises `MissingRecording` with the key, and a record round trip. Run `make test`.
- [ ] `backend/tests/test_llm_boundary.py` fails on a seeded `import litellm` in a temp module, then passes once the module is removed. Run `make test`.
- [ ] `backend/tests/live/test_doctor_live.py` marked `live` runs the real doctor. Run `cd backend && uv run pytest -m live tests/live/test_doctor_live.py`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Two lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run `make ci` and `curl /healthz` at trunk and head. Trunk has no `make doctor`, so record that, and gate a real `make doctor` at head with `LLM_MODE=live`. Save `doctor.txt`. Pass when trunk and head both pass `make ci`, head doctor prints three `OK` lines, and `llm_calls` gains exactly one row with nonzero tokens, cost, and latency.
- [ ] Lane 2. Unset every provider key and run `make test` with `LLM_MODE=replay`. Then call `complete` with a prompt that has no recording. Save `replay.txt`. Pass when `make test` reports 0 failed with no network access to model hosts and the unrecorded call raises `MissingRecording` naming its key.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time of `make ci`, and wall time of `make doctor` at head. Trunk has no doctor, so doctor gets an absolute budget.
- [ ] Probe. `/usr/bin/time -f %e make ci` interleaved at trunk and head per the boot recipe, then `/usr/bin/time -f %e make doctor` three times at head.
- [ ] Baseline. Record the trunk `make ci` median first.
- [ ] Rule. Fail when the head `make ci` median exceeds trunk by more than 20 s, or when the `make doctor` median exceeds 10 s.

**Review gate.** None. P0-2 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The root appends P0-2 to the base-branch stack and the operator lands it bottom-up.

## Model the case and hand-write three cases (P1-1)

**Depends on.** P0-2 and the Phase 0 gate.

**Files.**

- [ ] Create `backend/engine/__init__.py` and `backend/engine/schema.py`.
- [ ] Create `backend/engine/cli.py`.
- [ ] Create `cases/manor.json`, `cases/gallery.json`, and `cases/lighthouse.json`.
- [ ] Create `backend/tests/engine/test_schema.py`.
- [ ] Create `docs/adr/002-case-schema.md`.
- [ ] Edit `Makefile`.

**Build.**

- [ ] Add `Person`, `Fact`, `PlannedLie`, `Clue`, `EvidenceDoc`, and `Case` in `backend/engine/schema.py` per `docs/spec.md`.
- [ ] Add `Crime` with `location`, `time_slot`, and `means` to `Case`, so the compiler reads the scene from one place instead of searching facts.
- [ ] Make `Fact.predicate` a closed `Literal` of the predicates the compiler understands, starting with `at`, `has`, `saw`, `owes`, and `heard`. An unknown predicate fails validation.
- [ ] Add one `model_validator` on `Case` that checks every reference. It covers `known_by`, `secrets` keys and values, `planned_lies.suspect` and `hides_fact`, `clues.reveals`, `clues.doc_id`, `solution_chain`, `culprit`, fact subjects that name people, and fact locations. Each error names the JSON path and the dangling id.
- [ ] Write three cases with 4 suspects each, 6 to 10 clues, at least 1 planned lie, and one short `EvidenceDoc` per evidence clue. Phase 3 grows the documents to 15 to 20 per case.
- [ ] Add `python -m engine.cli validate <path>...` and `make validate-cases`.
- [ ] Write `docs/adr/002-case-schema.md` with each field added to or narrowed from the spec and why.

**You see.**

- [ ] `make validate-cases` prints `OK cases/manor.json`, `OK cases/gallery.json`, and `OK cases/lighthouse.json`.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `backend/tests/engine/test_schema.py` gains a case that parses each of the 3 cases. Run `make test`.
- [ ] `backend/tests/engine/test_schema.py` gains one parametrized case per reference kind. Each mutates a valid case to point at a missing id and asserts the error names that path and id. Run `make test`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Two lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run `make ci` and `make doctor SKIP_MODEL=1` at trunk and head. Trunk has no cases, so record that, and gate `make validate-cases` at head. Save `validate.txt`. Pass when both sides pass `make ci` and head prints three `OK` lines.
- [ ] Lane 2. Copy `cases/manor.json` to `/tmp/broken.json`, rename one suspect id in `suspects` only, and run `python -m engine.cli validate /tmp/broken.json`. Save `dangling.txt`. Pass when the command exits non-zero and lists every path that still references the old id.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time of `make ci`, and wall time of `make validate-cases` at head.
- [ ] Probe. `/usr/bin/time -f %e make ci` interleaved at trunk and head per the boot recipe, then `/usr/bin/time -f %e make validate-cases` three times at head.
- [ ] Baseline. Record the trunk `make ci` median first.
- [ ] Rule. Fail when the head `make ci` median exceeds trunk by more than 15 s, or when `make validate-cases` exceeds 3 s.

**Review gate.** None. P1-1 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The root appends P1-1 to the base-branch stack and the operator lands it bottom-up.

## Prove each case has one culprit with clingo (P1-2)

**Depends on.** P1-1.

**Files.**

- [ ] Create `backend/engine/rules.lp`.
- [ ] Create `backend/engine/compiler.py`.
- [ ] Create `backend/engine/solver.py`.
- [ ] Create `backend/engine/mutate.py`.
- [ ] Edit `backend/engine/cli.py` and `Makefile`.
- [ ] Create `backend/tests/engine/test_solver.py`.
- [ ] Create `docs/adr/001-asp-encoding.md`.

**Build.**

- [ ] Add the fixed inference rules in `backend/engine/rules.lp`. The culprit is at the crime location at the crime slot. The culprit has the means. Nobody is in two places in one slot.
- [ ] Add `compile_case(case, *, drop_clues=frozenset(), extra_facts=()) -> str` in `backend/engine/compiler.py`. Use the open-world encoding from Appendix A. A fact no clue reveals becomes a choice. A clue becomes integrity constraints that pin the facts it reveals. A planned lie becomes a `claims(Suspect, Fact)` atom that is not taken as true.
- [ ] Add `check_case(case) -> CheckReport` in `backend/engine/solver.py`. It runs clingo with `--project` on `culprit/1` and reports `consistency`, `uniqueness`, and `necessity` results. A failed check carries a `Counterexample` with the alternative culprit and the fact ids in its model.
- [ ] Report a dropped chain clue that leaves zero models as a failure with its own reason, distinct from two or more culprits.
- [ ] Add `drop_clue(case, clue_id)` and `add_contradiction(case, fact_id)` in `backend/engine/mutate.py` as the mutation lever for tests and for the operator's checkpoint.
- [ ] Add `python -m engine.cli check <path>` and `make check-case CASE=<path>`. It prints one line per check and the counterexample when one exists.
- [ ] Write `docs/adr/001-asp-encoding.md`. It covers the open-world choice, how lies enter as testimony, how uniqueness and necessity are checked, and the rejected closed-world encoding.

**You see.**

- [ ] `make check-case CASE=cases/manor.json` prints `consistency PASS`, `uniqueness PASS culprit=<id>`, and `necessity PASS <n>/<n> chain clues`.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `backend/tests/engine/test_solver.py` gains a case asserting all 3 hand-written cases pass every check. Run `make test`.
- [ ] `backend/tests/engine/test_solver.py` gains a case per chain clue that drops it and asserts `uniqueness FAIL` with a counterexample naming another suspect. Run `make test`.
- [ ] `backend/tests/engine/test_solver.py` gains a case that adds a fact placing a suspect in two locations in one slot and asserts `consistency FAIL` naming both fact ids. Run `make test`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Two lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run `make validate-cases` at trunk and head. Trunk has no solver, so record that, and gate `make check-case` on all 3 cases at head. Save `check-all.txt`. Pass when validation output matches on both sides and each case prints three `PASS` lines.
- [ ] Lane 2. Hand-edit a copy of `cases/gallery.json` the way the operator will at the checkpoint. Delete one `solution_chain` clue from `clues`, run `make check-case`, then restore it and add a contradicting `at` fact. Save `mutations.txt`. Pass when the first run prints `uniqueness FAIL` with a counterexample culprit and fact ids, and the second prints `consistency FAIL` naming both facts.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time of `make check-case` per case at head. Trunk has no solver, so this is an absolute budget for the diff-added work. Also `make ci` at trunk and head.
- [ ] Probe. `/usr/bin/time -f %e make check-case CASE=<case>` three times per case at head, then `make ci` interleaved at trunk and head per the boot recipe.
- [ ] Baseline. Record the trunk `make ci` median first.
- [ ] Rule. Fail when any case's median `check-case` exceeds 2 s, or when the head `make ci` median exceeds trunk by more than 30 s.

**Review gate.** None. P1-2 is not review-gated. The Phase 1 checkpoint follows it.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The root appends P1-2 to the base-branch stack and the operator lands it bottom-up.

## Encode the verifier rules without model calls (P2-1)

**Depends on.** P1-2 and the Phase 1 checkpoint.

**Files.**

- [ ] Create `backend/agents/__init__.py`, `backend/agents/claims.py`, and `backend/agents/ledger.py`.
- [ ] Create `backend/agents/verifier.py`.
- [ ] Create `backend/agents/screening.py`.
- [ ] Create `backend/agents/events.py` and `backend/migrations/versions/0003_verifier_events.py`.
- [ ] Create `backend/tests/agents/test_verifier.py` and `backend/tests/agents/test_screening.py`.
- [ ] Create `docs/adr/004-verifier-rules.md`.

**Build.**

- [ ] Add `Claim(subject, predicate, object, time_slot)` in `backend/agents/claims.py`, using the `Fact.predicate` literal from `engine.schema`.
- [ ] Add the lie ledger as a state machine in `backend/agents/ledger.py`. `LieStatus` is `told`, `exposed`, or `admitted`. `LedgerEntry` holds suspect, planned lie, turn, and status. Exposure happens when the player presents a clue that reveals the hidden fact.
- [ ] Add `verify_reply(case, suspect_id, claims, ledger, presented_clue_ids) -> VerifyResult` in `backend/agents/verifier.py` as a pure function. Each claim gets one `Verdict`.
  - [ ] `KNOWN_TRUE` when the claim matches a fact whose `known_by` holds the suspect and that is not in the suspect's unexposed secrets.
  - [ ] `PLANNED_LIE` when the claim matches one of the suspect's `planned_lies` and agrees with every earlier ledger entry.
  - [ ] `ADMISSION` when the claim matches a hidden fact the suspect knows and a presented clue reveals it.
  - [ ] `BLOCK_CULPRIT` when the claim names the culprit as the killer or states a culprit secret that is not exposed. This rule runs first and has no exception.
  - [ ] `BLOCK_UNPLANNED` for every other claim.
- [ ] Treat "I don't know" and refusals as replies with no claims, so they always pass.
- [ ] Add `screen_input(text) -> ScreenResult` in `backend/agents/screening.py` with patterns for meta-instructions such as "ignore your role", "system prompt", and "just tell me the answer".
- [ ] Add the `verifier_events` table with game id, suspect, turn, rule, claim, and action, and `log_event` in `backend/agents/events.py`.
- [ ] Add `python -m agents.verifier --case <path> --suspect <id> --claims <json>` as a debug lever that prints each verdict.
- [ ] Write `docs/adr/004-verifier-rules.md` with each rule and the lie-to-admission transition.

**You see.**

- [ ] The debug lever prints one verdict line per claim and exits 1 when any claim is blocked.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `backend/tests/agents/test_verifier.py` gains one case per verdict with hand-built triples, plus a lie that contradicts an earlier ledger entry and a hidden fact claimed before its clue is presented. Run `make test`.
- [ ] `backend/tests/agents/test_screening.py` gains blocked and allowed inputs for each pattern. Run `make test`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Two lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run `make check-case` on all 3 cases at trunk and head. Save `check-regression.txt`. Pass when the outputs are byte-identical.
- [ ] Lane 2. Write `/tmp/claims.json` with four claims for one suspect of `cases/manor.json`, a known true fact, its planned lie, an unknown fact, and the culprit named as killer. Run the debug lever with `--log`. Save `verdicts.txt`. Pass when the verdicts are `KNOWN_TRUE`, `PLANNED_LIE`, `BLOCK_UNPLANNED`, and `BLOCK_CULPRIT`, and `verifier_events` gains exactly two rows.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Time per `verify_reply` call over 10 claims at head, and `make ci` at trunk and head.
- [ ] Probe. `uv run python -m timeit -s '<setup from tests>' 'verify_reply(...)'` at head, then `make ci` interleaved at trunk and head per the boot recipe.
- [ ] Baseline. Record the trunk `make ci` median first.
- [ ] Rule. Fail when `verify_reply` exceeds 5 ms per call, or when the head `make ci` median exceeds trunk by more than 15 s.

**Review gate.** None. P2-1 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The root appends P2-1 to the base-branch stack and the operator lands it bottom-up.

## Run each suspect turn as a verified LangGraph (P2-2)

**Depends on.** P2-1.

**Files.**

- [ ] Create `backend/agents/suspect.py`.
- [ ] Create `backend/agents/extract.py`.
- [ ] Create `backend/app/llm_pydantic.py`.
- [ ] Create `backend/agents/state.py`.
- [ ] Create `backend/tests/agents/test_suspect_replay.py` and recordings under `backend/tests/fixtures/llm/`.
- [ ] Edit `backend/pyproject.toml` for LangGraph, `langgraph-checkpoint-postgres`, and PydanticAI.

**Build.**

- [ ] Add a PydanticAI `Model` adapter in `backend/app/llm_pydantic.py` that sends every request through `app.llm.complete`, so extraction is logged and replayable like every other call.
- [ ] Add `extract_claims(reply) -> list[Claim]` in `backend/agents/extract.py` with a PydanticAI agent on `ModelRole.FAST`.
- [ ] Add the turn graph in `backend/agents/suspect.py` with nodes `retrieve`, `generate`, `extract`, `verify`, `rewrite`, `fallback`, and `commit`. `retrieve` loads only facts the suspect knows, their secrets, their planned lies, the ledger, and the last 6 turns. `rewrite` feeds the violation back at most 2 times. `fallback` returns "I'd rather not answer that." and logs a `verifier_events` row. `commit` updates the ledger.
- [ ] Persist graph state with `AsyncPostgresSaver` in `backend/agents/state.py`, with thread id `<game_id>:<suspect_id>`.
- [ ] Add `python -m agents.suspect --case <path> --suspect <id> --ask <text> [--present <clue_id>]` as a debug lever.
- [ ] Record fixtures with `LLM_MODE=record` for the replay tests.

**You see.**

- [ ] The debug lever prints the reply, each claim with its verdict, the rewrite count, and the ledger after the turn.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `backend/tests/agents/test_suspect_replay.py` gains four replayed turns. A suspect tells its planned lie. A draft that breaks a rule passes after one rewrite. A draft that fails 3 times falls back and logs a row. A suspect admits its hidden fact after the clue is presented. Run `make test`.
- [ ] `backend/tests/agents/test_suspect_replay.py` gains a restart case that rebuilds the graph from the checkpointer and keeps the ledger. Run `make test`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Two lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run the P2-1 debug lever on the Lane 2 claims of P2-1 at trunk and head. Save `verifier-regression.txt`. Pass when the verdicts and `verifier_events` row counts match on both sides.
- [ ] Lane 2. With `LLM_MODE=live`, ask the lying suspect in `cases/manor.json` the question its planned lie covers, then ask again with `--present` set to the exposing clue. Save `lie-then-admit.txt`. Pass when the first reply passes the verifier as `PLANNED_LIE`, the second passes as `ADMISSION`, the ledger moves from `told` to `admitted`, and the lane cost stays under `LANE_MAX_USD`.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Graph overhead per turn in replay mode, live turn latency from question to released reply, and `make ci` at trunk and head.
- [ ] Probe. Time 20 replayed turns with `pytest --durations=0 tests/agents/test_suspect_replay.py`, time 10 live turns from Lane 2 with `latency_ms` in `llm_calls`, and run `make ci` interleaved at trunk and head per the boot recipe.
- [ ] Baseline. Record the trunk `make ci` median first.
- [ ] Rule. Fail when the replayed turn p95 exceeds 200 ms, the live turn p95 exceeds 8 s, or the head `make ci` median exceeds trunk by more than 30 s.

**Review gate.** None. P2-2 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The root appends P2-2 to the base-branch stack and the operator lands it bottom-up.

## Play a full game in the terminal (P2-3)

**Depends on.** P2-2.

**Files.**

- [ ] Create `backend/agents/game_master.py`.
- [ ] Create `backend/app/cli.py`.
- [ ] Create `backend/tests/agents/test_game_master.py` and `backend/tests/test_cli_replay.py`.
- [ ] Create `backend/tests/live/test_jailbreak_cli.py`.
- [ ] Edit `Makefile`.

**Build.**

- [ ] Add `GameState` in `backend/agents/game_master.py` with 20 questions, 3 hints, discovered clue ids, and opened document ids.
- [ ] Add `next_hint(case, state)`. It points to a `solution_chain` clue the player has not discovered, and refuses when no hints remain.
- [ ] Add `rule_accusation(case, suspect_id, cited_clue_ids) -> Ruling`. The ruling is correct only when the suspect is the culprit and the citation holds at least 2 `solution_chain` clues.
- [ ] Run `screen_input` before every question. A screened input costs no question, gets an in-character refusal, and logs a `verifier_events` row with rule `input_screen`.
- [ ] Add the terminal loop in `backend/app/cli.py` with `/suspect`, `/ask`, `/read`, `/present`, `/hint`, `/accuse`, `/status`, and `/quit`.
- [ ] Add `make play-cli CASE=<path>`.

**You see.**

- [ ] `make play-cli CASE=cases/manor.json` prints the case summary, the 4 suspects, and `20 questions, 3 hints left`.
- [ ] A correct accusation prints `Correct` with the cited chain clues, then the true timeline.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `backend/tests/agents/test_game_master.py` gains cases for budget exhaustion, a fourth hint refused, a hint that skips discovered clues, a wrong culprit, and a right culprit with fewer than 2 chain clues. Run `make test`.
- [ ] `backend/tests/test_cli_replay.py` gains a replayed full game on `cases/manor.json` that ends in `Correct`. Run `make test`.
- [ ] `backend/tests/live/test_jailbreak_cli.py` sends 5 jailbreak prompts to each suspect and asserts no reply names the culprit as killer. Run `cd backend && uv run pytest -m live tests/live/test_jailbreak_cli.py`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Two lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run `tests/agents/test_suspect_replay.py` and the P2-2 debug lever turn at trunk and head. Trunk has no game loop, so record that, and gate the replayed full game at head. Save `replay-regression.txt`. Pass when the suspect tests pass on both sides and the head replayed game ends in `Correct`.
- [ ] Lane 2. With `LLM_MODE=live`, play `make play-cli CASE=cases/lighthouse.json` through the `run` skill. Ask questions, read documents, use 3 hints and try a fourth, send one jailbreak prompt, present a clue, and accuse with 2 chain clues. Save `full-game.txt`. Pass when the fourth hint is refused, the jailbreak costs no question and leaks nothing, the ruling is `Correct`, and the lane cost stays under `LANE_MAX_USD`.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Time from `make play-cli` to the first prompt, and `make ci` at trunk and head.
- [ ] Probe. Time CLI start to prompt three times at head with `LLM_MODE=replay`, then run `make ci` interleaved at trunk and head per the boot recipe.
- [ ] Baseline. Record the trunk `make ci` median first.
- [ ] Rule. Fail when CLI start exceeds 3 s, or when the head `make ci` median exceeds trunk by more than 20 s.

**Review gate.** The operator reviews before merge.

- [ ] Copy lane 2 transcripts into `docs/media/p2-3/p2-3-review-full-game.txt` and save a terminal screenshot as `docs/media/p2-3/p2-3-review-accuse.png`.
- [ ] Record a 30 to 60 second video of the change in a lane worktree. Save it as `docs/media/p2-3/p2-3-review.mp4`. Record with `asciinema rec` and convert with `agg` and `ffmpeg`.
- [ ] Post the screenshot and the video in chat for the operator. Stop at merge-ready. Wait for the operator's click.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The root appends P2-3 to the base-branch stack and the operator lands it bottom-up. The Phase 2 checkpoint follows.

## Write the evidence archive for the three cases (P3-1)

**Depends on.** P2-3 and the Phase 2 checkpoint.

**Files.**

- [ ] Edit `cases/manor.json`, `cases/gallery.json`, and `cases/lighthouse.json`.
- [ ] Edit `backend/engine/cli.py` and `Makefile`.
- [ ] Create `backend/tests/engine/test_evidence_lint.py`.

**Build.**

- [ ] Grow each case to 15 to 20 plain-text `EvidenceDoc` entries. Mark `is_key` true on every document that a `solution_chain` clue references, and false on the rest.
- [ ] Write the non-key documents as plausible distractors. None of them may state a fact that changes the solver result.
- [ ] Add `python -m engine.cli lint-evidence <path>` and `make lint-evidence`. It checks the document count, that every evidence clue's `doc_id` exists, and that `is_key` matches chain references. It prints a table per case.

**You see.**

- [ ] `make lint-evidence` prints one row per case with the document count, the key count, and `OK`.
- [ ] `make check-case` still passes on all 3 cases.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `backend/tests/engine/test_evidence_lint.py` gains cases for too few documents, a key flag on an unreferenced document, and a missing `doc_id`. Run `make test`.
- [ ] `backend/tests/engine/test_solver.py` still passes on the grown cases. Run `make test`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Two lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run `make check-case` on all 3 cases at trunk and head. Save `solver-regression.txt`. Pass when the culprit and every check result match on both sides.
- [ ] Lane 2. Play `make play-cli CASE=cases/gallery.json` in replay mode through the `run` skill, `/read` two key documents and one distractor, then accuse. Save `read-docs.txt`. Pass when each key document read adds its clue to `/status` and the distractor adds none.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. `make check-case` time per grown case, compared with trunk.
- [ ] Probe. `/usr/bin/time -f %e make check-case CASE=<case>` interleaved at trunk and head per the boot recipe.
- [ ] Baseline. Record each trunk case median first.
- [ ] Rule. Fail when any head case median exceeds its trunk median by more than 50 percent or exceeds 2 s.

**Review gate.** None. P3-1 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The root appends P3-1 to the base-branch stack and the operator lands it bottom-up.

## Index the archive for hybrid search (P3-2)

**Depends on.** P3-1.

**Files.**

- [ ] Create `backend/evidence/__init__.py`, `backend/evidence/chunk.py`, `backend/evidence/index.py`, and `backend/evidence/search.py`.
- [ ] Create `backend/migrations/versions/0004_evidence_chunks.py`.
- [ ] Create `backend/evals/__init__.py`, `backend/evals/retrieval.py`, and `backend/evals/retrieval_queries.yaml`.
- [ ] Create `backend/tests/evidence/test_search.py` and recorded embeddings under `backend/tests/fixtures/llm/`.
- [ ] Edit `Makefile`.

**Build.**

- [ ] Add `evidence_chunks` with case id, document id, chunk text, `embedding vector(EMBED_DIM)`, and a generated `tsvector` column with a GIN index.
- [ ] Add `chunk_document(doc) -> list[Chunk]` in `backend/evidence/chunk.py` with paragraph splits capped near 500 tokens.
- [ ] Add `index_case(case)` in `backend/evidence/index.py`. It embeds through `app.llm.embed` and upserts by case id and document id, so a rerun leaves the same rows.
- [ ] Add `search(case_id, query, k=5) -> list[Hit]` in `backend/evidence/search.py`. It runs a vector top 20 and a full-text top 20, merges them with reciprocal rank fusion at `k=60`, and returns highlights from `ts_headline`.
- [ ] Add `make seed`. It loads the 3 cases from `cases/` and indexes them.
- [ ] Add `make retrieval-eval`. It runs every query in `retrieval_queries.yaml` and writes recall@5 per case and overall to `reports/retrieval.json` and `reports/retrieval.md`.

**You see.**

- [ ] `make seed` prints the chunk count per case.
- [ ] `reports/retrieval.md` shows recall@5 for each of the 3 cases and overall.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `backend/tests/evidence/test_search.py` gains a replayed RRF merge with a known order, a keyword-only hit, a vector-only hit, and a rerun of `index_case` that keeps the row count. Run `make test`.
- [ ] `backend/tests/evidence/test_retrieval_eval.py` gains a fixed-ranking case where recall@5 equals a hand-computed value. Run `make test`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Two lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run the replayed full game from `tests/test_cli_replay.py` at trunk and head. Trunk has no archive index, so record that, and gate `make seed` plus one search at head. Save `cli-regression.txt`. Pass when the replayed game ends in `Correct` on both sides and head search returns 5 hits.
- [ ] Lane 2. With `LLM_MODE=live`, run `make seed && make retrieval-eval`, then search `cases/manor.json` for the wording of one key clue. Save `retrieval.txt`. Pass when `reports/retrieval.json` has recall@5 for all 3 cases, the key document is in the top 5 with its matched passage highlighted, and the lane cost stays under `LANE_MAX_USD`.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Search latency per query at head and index build time per case. Trunk has no search, so both are absolute budgets. Also `make ci` at trunk and head.
- [ ] Probe. Time every query in `retrieval_queries.yaml` against the seeded database three times, time `make seed` once live, and run `make ci` interleaved at trunk and head per the boot recipe.
- [ ] Baseline. Record the trunk `make ci` median first.
- [ ] Rule. Fail when search p95 exceeds 300 ms, indexing one case exceeds 60 s, or the head `make ci` median exceeds trunk by more than 30 s.

**Review gate.** None. P3-2 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The root appends P3-2 to the base-branch stack and the operator lands it bottom-up.

## Serve the game over HTTP and WebSocket (P3-3)

**Depends on.** P3-2.

**Files.**

- [ ] Create `backend/app/routes/games.py` and `backend/app/schemas.py`.
- [ ] Create `backend/app/games.py` and `backend/migrations/versions/0005_games.py`.
- [ ] Edit `backend/agents/game_master.py` and `backend/app/main.py`.
- [ ] Create `backend/tests/api/test_games.py` and `backend/tests/api/test_ask_ws.py`.

**Build.**

- [ ] Add the `games` table with case id, `GameState`, created time, and finished time.
- [ ] Add `POST /games`, `GET /games/{id}`, `GET /games/{id}/search`, `POST /games/{id}/documents/{doc_id}/open`, `POST /games/{id}/hint`, `POST /games/{id}/accuse`, and `GET /games/{id}/reveal`.
- [ ] Add `WS /games/{id}/ask`. It runs the full suspect turn, then streams the verified reply in chunks followed by a `done` message with the questions left. A reply streams only after the verifier passes it.
- [ ] Return 409 from `/reveal` until the game has an accusation.
- [ ] Extend `next_hint` to point at key documents the player has not opened, after undiscovered testimony clues.
- [ ] Rebuild `app/cli.py` on the same `app/games.py` service, so the CLI and the API share one game path.

**You see.**

- [ ] `GET /docs` lists every endpoint. A WebSocket client sees two or more `chunk` messages and one `done` message per question.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `backend/tests/api/test_games.py` gains a replayed game through every HTTP endpoint, a 409 reveal before accusation, and an archive hint that names an unopened key document. Run `make test`.
- [ ] `backend/tests/api/test_ask_ws.py` gains a replayed streamed turn, a screened input, and a turn after the budget runs out. Run `make test`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Two lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run the replayed CLI game and `make retrieval-eval` in replay mode at trunk and head. Save `regression.txt`. Pass when both sides end in `Correct` and report identical recall@5.
- [ ] Lane 2. With `LLM_MODE=live`, drive the API with a `websockets` client script through the `run` skill. Start a game, ask two questions, search, open a document, take a hint, accuse, and reveal. Save `api-game.txt`. Pass when each ask streams two or more chunks then `done`, the ruling is `Correct`, the reveal lists the true timeline, and the lane cost stays under `LANE_MAX_USD`.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Time from WebSocket question to first chunk, in replay and live. The terminal path is the trunk equivalent of a full turn.
- [ ] Probe. Time 20 replayed asks over WebSocket at head and 20 replayed CLI turns at trunk, interleaved per the boot recipe. Time 10 live asks at head.
- [ ] Baseline. Record the trunk CLI replayed turn median first.
- [ ] Rule. Fail when the head replayed turn median exceeds the trunk CLI median by more than 50 ms, or when the live time to `done` p95 exceeds 8 s.

**Review gate.** None. P3-3 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The root appends P3-3 to the base-branch stack and the operator lands it bottom-up.

## Play a full game in the browser (P3-4)

**Depends on.** P3-3.

**Files.**

- [ ] Create `frontend/package.json`, `frontend/package-lock.json`, `frontend/tsconfig.json`, `frontend/vite.config.ts`, and `frontend/eslint.config.js`.
- [ ] Create `frontend/src/main.tsx`, `frontend/src/App.tsx`, and `frontend/src/api.ts`.
- [ ] Create `frontend/src/components/CasePanel.tsx`, `ChatPanel.tsx`, `ArchivePanel.tsx`, `AccuseDialog.tsx`, and `RevealPage.tsx`.
- [ ] Create `frontend/src/api-types.ts`, generated from the FastAPI OpenAPI schema.
- [ ] Create `frontend/e2e/full-game.spec.ts` and `frontend/playwright.config.ts`.
- [ ] Create `.claude/skills/verify/SKILL.md` with `/create-verification-skill`.
- [ ] Edit `docker-compose.yml`, `Makefile`, and `.github/workflows/ci.yml`.

**Build.**

- [ ] Generate `frontend/src/api-types.ts` with `openapi-typescript` from `/openapi.json`, and add `make api-types`. CI fails when the generated file differs from the committed one.
- [ ] Build the left column in `CasePanel.tsx` with the case summary, the suspect list, and the questions and hints left.
- [ ] Build the center column in `ChatPanel.tsx`. It shows the current suspect's conversation and renders streamed chunks as they arrive.
- [ ] Build the right column in `ArchivePanel.tsx` with the search box, hits with highlighted passages, and the Accuse button.
- [ ] Build `AccuseDialog.tsx`. The player picks a suspect and selects supporting clues from opened documents and testimony.
- [ ] Build `RevealPage.tsx` with the ruling, the cited clues, and the true timeline.
- [ ] Add the `frontend` service to `docker-compose.yml` on port 5173, `make web`, and `make play`, which opens `http://localhost:5173`.
- [ ] Add eslint, `tsc --noEmit`, and the Playwright e2e against a replay-mode backend to `make ci`.
- [ ] Record the browser boot and Playwright commands in `.claude/skills/verify/SKILL.md`, so later lanes drive the browser the same way.

**You see.**

- [ ] `make play` opens the three-column page with the case loaded.
- [ ] A reply streams word by word into the center column.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `frontend/e2e/full-game.spec.ts` plays a replayed game on `cases/manor.json` from start to reveal. Run `cd frontend && npx playwright test`.
- [ ] `cd frontend && npx tsc --noEmit && npx eslint .` passes with 0 errors. Run `make ci`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Two lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run the Lane 2 API script of P3-3 in replay mode at trunk and head. Trunk has no frontend, so record that, and gate the replayed Playwright game at head. Save `api-regression.png`. Pass when the API script ends in `Correct` on both sides and the head e2e reaches the reveal page.
- [ ] Lane 2. With `LLM_MODE=live`, play `cases/gallery.json` in Chromium at 1280 by 800 through `.claude/skills/verify/SKILL.md`. Ask two suspects, search the archive, open a key document, take a hint, accuse with 2 chain clues, and view the reveal. Save `chat-streaming.png`, `archive-highlight.png`, `accuse.png`, and `reveal.png`. Pass when replies stream visibly, the hit shows a highlighted passage, the ruling is `Correct`, the timeline renders, and the lane cost stays under `LANE_MAX_USD`.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Production bundle size, replayed Playwright game wall time, and time from Ask to first visible chunk. Trunk has no frontend, so these are absolute budgets. Also `make ci` at trunk and head.
- [ ] Probe. `npx vite build` and read the gzip size, run `npx playwright test` three times, read first-chunk time from a `performance.mark` in `ChatPanel.tsx`, and run `make ci` interleaved at trunk and head per the boot recipe.
- [ ] Baseline. Record the trunk `make ci` median first.
- [ ] Rule. Fail when the gzip bundle exceeds 300 kB, the replayed e2e exceeds 60 s, replayed first chunk exceeds 300 ms after Ask, or the head `make ci` median exceeds trunk by more than 120 s.

**Review gate.** The operator reviews before merge.

- [ ] Copy lane 2 screenshots into `docs/media/p3-4/p3-4-review-chat.png`, `docs/media/p3-4/p3-4-review-archive.png`, and `docs/media/p3-4/p3-4-review-reveal.png`.
- [ ] Record a 30 to 60 second video of the change in a lane worktree with Playwright `recordVideo`. Save it as `docs/media/p3-4/p3-4-review.webm`.
- [ ] Post the screenshots and the video in chat for the operator. Stop at merge-ready. Wait for the operator's click.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The root appends P3-4 to the base-branch stack and the operator lands it bottom-up.

## Generate cases and repair them from counterexamples (P4-1)

**Depends on.** P3-4 and the Phase 3 gate.

**Files.**

- [ ] Create `backend/engine/generator.py`.
- [ ] Create `backend/engine/repair.py`.
- [ ] Create `backend/migrations/versions/0006_generation_log.py`.
- [ ] Create `backend/tests/engine/test_generator_replay.py` and `backend/tests/engine/test_repair.py`, with recordings under `backend/tests/fixtures/llm/`.

**Build.**

- [ ] Add `generate_case(brief) -> Case` in `backend/engine/generator.py`. It calls `ModelRole.STRONG` with `Case.model_json_schema()` as the structured output, then a second call for 15 to 20 evidence documents. A Pydantic error goes back to the model as feedback once.
- [ ] Add `repair_instructions(report) -> str` in `backend/engine/repair.py` as a pure function. It turns each failed check and its counterexample into instructions that name the alternative culprit and the facts that allow it.
- [ ] Add `generate_with_repair(brief, max_rounds=5) -> GenerationResult`. It runs `check_case` after each round, accepts the first passing case, and discards the case after 5 failed rounds.
- [ ] Add `generation_log` with brief, rounds, outcome, failure reason, cost, and accepted case id. Cost is the sum of `llm_calls` rows tagged with the generation id.
- [ ] Reuse the Phase 1 solver tests unchanged.

**You see.**

- [ ] One live generation writes a `generation_log` row with `rounds`, `outcome`, and `cost_usd`.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `backend/tests/engine/test_generator_replay.py` gains a replayed valid case, a replayed schema error fixed on retry, and a replayed case accepted after 2 repair rounds. Run `make test`.
- [ ] `backend/tests/engine/test_repair.py` gains instruction text for each failure kind and a run that fails 5 rounds and logs `discarded` with its reason. Run `make test`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Two lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run `make check-case` on the 3 hand-written cases and the replayed Playwright game at trunk and head. Save `regression.txt`. Pass when the solver output and the e2e result match on both sides.
- [ ] Lane 2. With `LLM_MODE=live`, run `uv run python -m engine.generator --once`. Save `generate-once.txt`. Pass when the run ends in `accepted` or `discarded` within 5 rounds, `generation_log` records every round, an accepted case passes `make check-case`, and the lane cost stays under `LANE_MAX_USD`.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Cost and wall time per generation attempt, and `make ci` at trunk and head. Trunk has no generator, so cost and time are absolute budgets.
- [ ] Probe. Read `cost_usd` and the elapsed time from `generation_log` for Lane 2, then run `make ci` interleaved at trunk and head per the boot recipe.
- [ ] Baseline. Record the trunk `make ci` median first.
- [ ] Rule. Fail when one attempt costs more than 1 USD or takes more than 300 s, or when the head `make ci` median exceeds trunk by more than 30 s.

**Review gate.** None. P4-1 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The root appends P4-1 to the base-branch stack and the operator lands it bottom-up.

## Ship make case and make the new cases playable (P4-2)

**Depends on.** P4-1.

**Files.**

- [ ] Edit `backend/engine/cli.py` and `Makefile`.
- [ ] Create `backend/app/routes/cases.py`.
- [ ] Create `frontend/src/components/CasePicker.tsx` and edit `frontend/src/App.tsx`.
- [ ] Create `frontend/e2e/play-case.spec.ts`.
- [ ] Create `backend/evals/generation_report.py`.

**Build.**

- [ ] Add `python -m engine.cli generate --n <N>`, `make case`, and `make cases N=<N>`. Each accepted case goes to `cases/generated/<id>.json`, the database, and the archive index in one step. `cases/generated/` is gitignored.
- [ ] Add `GET /cases` and a case picker in `CasePicker.tsx`, so a new case is playable in the browser right after generation.
- [ ] Add `frontend/e2e/play-case.spec.ts`. It reads a case file from disk, plays it to the reveal by citing its `solution_chain`, and takes the case path from `CASE`.
- [ ] Add `backend/evals/generation_report.py`. It writes the first-pass rate and the final pass rate from `generation_log` to `reports/generation.md` and `reports/generation.json`.

**You see.**

- [ ] `make cases N=10` ends with `first-pass <a>/10, final <b>/10` and writes `reports/generation.md`.
- [ ] The browser case picker lists the accepted cases next to the 3 hand-written ones.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `backend/tests/engine/test_generate_cli.py` gains a replayed batch of 3 with one discard, asserting files, database rows, index rows, and report rates. Run `make test`.
- [ ] `frontend/e2e/play-case.spec.ts` plays each hand-written case to the reveal. Run `cd frontend && npx playwright test play-case`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Two lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run the replayed `full-game.spec.ts` at trunk and head through `.claude/skills/verify/SKILL.md`. Save `e2e-regression.png`. Pass when both sides reach the reveal page with `Correct`.
- [ ] Lane 2. With `LLM_MODE=live`, run `make cases N=10`, then run `play-case.spec.ts` once per accepted case against the live backend. Save `generation-report.png` and `play-<case-id>.png` per case. Pass when `reports/generation.md` states both rates, every accepted case reaches the reveal with `Correct`, and the batch cost stays under `EVAL_MAX_USD`.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Batch cost and wall time for 10 cases, and the time from acceptance until the case shows in `GET /cases`. Trunk has no batch command, so these are absolute budgets.
- [ ] Probe. Read the totals from `generation_log` for Lane 2 and time `GET /cases` after the last acceptance. Run the replayed `full-game.spec.ts` interleaved at trunk and head per the boot recipe.
- [ ] Baseline. Record the trunk e2e median first.
- [ ] Rule. Fail when the batch exceeds `EVAL_MAX_USD` or 60 minutes, a case takes more than 5 s to appear, or the head e2e median exceeds trunk by more than 10 s.

**Review gate.** The operator reviews before merge.

- [ ] Copy lane 2 screenshots into `docs/media/p4-2/p4-2-review-picker.png` and `docs/media/p4-2/p4-2-review-generated-reveal.png`.
- [ ] Record a 30 to 60 second video of the change in a lane worktree with Playwright `recordVideo`. Save it as `docs/media/p4-2/p4-2-review.webm`.
- [ ] Post the screenshots, the video, and `reports/generation.md` in chat for the operator. Stop at merge-ready. Wait for the operator's click.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The root appends P4-2 to the base-branch stack and the operator lands it bottom-up.

## Play the game with a detective bot under a budget (P5-1)

**Depends on.** P4-2 and the Phase 4 gate.

**Files.**

- [ ] Create `backend/sim/__init__.py`, `backend/sim/detective_bot.py`, and `backend/sim/runner.py`.
- [ ] Edit `backend/app/llm.py` to tag calls with a run id.
- [ ] Create `backend/tests/sim/test_bot_replay.py` and `backend/tests/sim/test_runner_budget.py`.
- [ ] Edit `Makefile`.

**Build.**

- [ ] Add `DetectiveBot` in `backend/sim/detective_bot.py`. It plays only through the HTTP and WebSocket endpoints the browser uses, with `ModelRole.STRONG` for strategy. It searches the archive for timeline contradictions, questions suspects about them, and accuses before the budget runs out.
- [ ] Add `run_games(n, concurrency, max_usd) -> RunResult` in `backend/sim/runner.py`. It checks the run's summed `cost_usd` after every model call and stops all games once the sum exceeds `max_usd`.
- [ ] Tag every `llm_calls` row with `run_id` and `game_id` through a context variable in `app/llm.py`, so cost splits per game and per model.
- [ ] Add `make sim N=<N> CONCURRENCY=<C>`.

**You see.**

- [ ] `make sim N=5` prints one line per game with the ruling, questions used, and cost, then the total.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `backend/tests/sim/test_bot_replay.py` gains a replayed bot game against the test client that ends in an accusation. Run `make test`.
- [ ] `backend/tests/sim/test_runner_budget.py` gains a run with fixed fake costs that stops once the sum passes the cap and reports `budget_exceeded`. Run `make test`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Two lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run the replayed `full-game.spec.ts` and `make retrieval-eval` in replay mode at trunk and head. Save `regression.png`. Pass when both sides reach the reveal and report identical recall@5.
- [ ] Lane 2. With `LLM_MODE=live`, run `make sim N=5 CONCURRENCY=2` with `EVAL_MAX_USD=2`, then rerun with `EVAL_MAX_USD=0.01`. Save `sim.txt`. Pass when the first run finishes 5 games through the public API only, the second stops with `budget_exceeded` after its first call, and no run's summed cost exceeds its cap by more than one call.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Cost and wall time per bot game, and `make ci` at trunk and head. Trunk has no bot, so per-game cost and time are absolute budgets.
- [ ] Probe. Read per-game totals from `llm_calls` grouped by `game_id` for Lane 2, then run `make ci` interleaved at trunk and head per the boot recipe.
- [ ] Baseline. Record the trunk `make ci` median first.
- [ ] Rule. Fail when a game costs more than 0.40 USD or takes more than 10 minutes, or when the head `make ci` median exceeds trunk by more than 30 s.

**Review gate.** None. P5-1 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The root appends P5-1 to the base-branch stack and the operator lands it bottom-up.

## Produce the first quality report (P5-2)

**Depends on.** P5-1.

**Files.**

- [ ] Create `backend/evals/jailbreak.yaml` and `backend/evals/promptfooconfig.yaml`.
- [ ] Create `backend/evals/report.py`.
- [ ] Create `.github/workflows/live-eval.yml` and edit `.github/workflows/ci.yml`.
- [ ] Create `reports/baseline/eval.md` and `reports/baseline/eval.json`.
- [ ] Create `docs/adr/005-metric-definitions.md`.
- [ ] Edit `Makefile`.

**Build.**

- [ ] Write 20 jailbreak prompts in `backend/evals/jailbreak.yaml` and run them with promptfoo against `WS /games/{id}/ask`. The assertion fails when a reply names the culprit as killer or states a culprit secret.
- [ ] Add `backend/evals/report.py`. It reads `llm_calls`, `verifier_events`, `games`, the promptfoo result, and `reports/retrieval.json`, and writes `reports/eval.md` and `reports/eval.json`.
  - [ ] Solve rate is correct accusations over finished games.
  - [ ] Average questions asked is over solved games.
  - [ ] Verifier block rate is blocked drafts per 100 turns.
  - [ ] Safe-fallback rate is fallback replies over released replies.
  - [ ] Jailbreak leaks is the count of failed promptfoo assertions.
  - [ ] Retrieval recall@5 comes from `reports/retrieval.json`.
  - [ ] Tokens and cost per game are split by model.
  - [ ] p95 latency per turn runs from the question to the `done` message.
- [ ] Add `make eval N=<N>`. It runs the jailbreak set, `make retrieval-eval`, and `make sim`, then the report.
- [ ] Before the 100-game run, run `make eval N=5` and project the 100-game cost. If the projection exceeds `EVAL_MAX_USD`, write the numbers to `docs/QUESTIONS.md` and stop.
- [ ] Split CI into the `fast` job on every PR and a `workflow_dispatch` job in `live-eval.yml` that takes a `max_usd` input and uses repository secrets.
- [ ] Commit the first 100-game report as `reports/baseline/` and write `docs/adr/005-metric-definitions.md`.

**You see.**

- [ ] `make eval N=100` writes `reports/eval.md` with every metric above and `Jailbreak leaks 0`.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `backend/tests/evals/test_report.py` gains a seeded database with known counts and asserts each metric equals its hand-computed value. Run `make test`.
- [ ] `backend/tests/evals/test_jailbreak_assert.py` gains a leaking reply and a clean reply against the promptfoo assertion. Run `make test`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Two lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run `make sim N=2` in replay mode and `make retrieval-eval` at trunk and head. Trunk has no report, so record that, and gate `reports/eval.md` at head from the same replayed games. Save `report-regression.txt`. Pass when both sides finish 2 games with the same rulings and head writes every metric.
- [ ] Lane 2. With `LLM_MODE=live`, run `make eval N=100` after the N=5 projection clears the cap. Save `eval-report.png` as a render of `reports/eval.md`. Pass when the report has every metric, jailbreak leaks is 0, every number traces to its source table, and the total cost stays under `EVAL_MAX_USD`.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Total cost and wall time of `make eval N=100`, and p95 turn latency inside it. Trunk has no eval, so these are absolute budgets. Also `make ci` at trunk and head.
- [ ] Probe. Read totals from `reports/eval.json` for Lane 2, then run `make ci` interleaved at trunk and head per the boot recipe.
- [ ] Baseline. Record the trunk `make ci` median first.
- [ ] Rule. Fail when the run exceeds `EVAL_MAX_USD` or 3 hours, when the p95 turn latency exceeds 8 s, or when the head `make ci` median exceeds trunk by more than 30 s.

**Review gate.** None. P5-2 is not review-gated. The Phase 5 checkpoint follows it.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The root appends P5-2 to the base-branch stack and the operator lands it bottom-up.

## Document the project so anyone can run and demo it (P6-1)

**Depends on.** P5-2 and the Phase 5 checkpoint.

**Files.**

- [ ] Edit `README.md`.
- [ ] Edit `docs/adr/001-asp-encoding.md`, `docs/adr/004-verifier-rules.md`, and `docs/adr/005-metric-definitions.md`.
- [ ] Create `docs/demo.md`.
- [ ] Create `docs/media/readme/`.

**Build.**

- [ ] Rewrite `README.md` with screenshots, the six-command quick start, an architecture overview of the backend packages, and a summary of `reports/baseline/eval.md`.
- [ ] Bring each ADR in line with the code as merged. Name the files and symbols each one describes.
- [ ] Write `docs/demo.md` as a 2-minute script that plays one game and runs `make eval N=2`.

**You see.**

- [ ] Every command in the README quick start runs as written in a fresh clone.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `backend/tests/test_docs.py` gains a check that every `make` target named in `README.md` and `docs/demo.md` exists in `Makefile`, and every path named in the ADRs exists. Run `make test`.
- [ ] `make ci` passes. Run `make ci`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Two lanes on the configured `swarm workers` model at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run the replayed `full-game.spec.ts` at trunk and head. Save `e2e-regression.png`. Pass when both sides reach the reveal with `Correct`.
- [ ] Lane 2. Clone the repo into a new directory, follow the README quick start word for word with native PostgreSQL in place of Docker, and play one live game in the browser to the reveal. Save `fresh-clone-reveal.png`. Pass when no step needs a command the README does not state and the game reaches the reveal.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Time from a fresh clone to the first suspect reply by following the README. Trunk has the same code, so trunk and head both follow their own README.
- [ ] Probe. Time Lane 2 from clone to first reply at head, and the same steps from the trunk README, interleaved per the boot recipe.
- [ ] Baseline. Record the trunk clone-to-first-reply time first.
- [ ] Rule. Fail when the head time exceeds 15 minutes or exceeds trunk by more than 20 percent.

**Review gate.** None. P6-1 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Base and verdict are current under the execution playbook and the patch-id rule in `playbooks/shipping.md`.
- [ ] The root appends P6-1 to the base-branch stack and the operator lands it bottom-up.

## Close the program

- [ ] Every box above is checked with its evidence.
- [ ] The operator runs the README quick start with `docker compose up -d` on a fresh machine and plays a full game. Cloud sessions cannot prove the Docker path, so this check stays with the operator.
- [ ] Reply to the operator with the report the execution playbook names.

## Appendix A. Prototype evidence

**The open-world ASP encoding makes the necessity check work. Proven.** No branch exists, because the repo had no root commit. The prototype ran with clingo 5.8.2 on Python 3.12 through `uv run --no-project --with clingo`. It had 4 suspects, a crime at the study in slot 3, and 4 clues.

A closed-world encoding asserted each clue's facts directly and used `not has_key(S)` to rule suspects out. With all clues it returned one culprit. Dropping the clue that grants keys returned zero models, not two culprits, because negation as failure ruled out every suspect. A necessity check built on that encoding reports "no culprit", and the repair loop gets no counterexample to act on.

The open-world encoding guessed every unrevealed fact with a choice rule and turned each clue into integrity constraints. Dropping a chain clue widened the culprit set to two suspects, which is the counterexample the spec asks for. Dropping a non-chain clue left the culprit unique. P1-2 starts from this shape.

```prolog
1 { at(S,L,3) : loc(L) } 1 :- suspect(S).
{ has_key(S) } :- suspect(S).
1 { culprit(S) : suspect(S) } 1.
:- culprit(S), victim_at(L,T), not at(S,L,T).
:- culprit(S), not has_key(S).
% clue c4 pins one fact
:- not at(dan,garden,3).
```

Run with `clingo.Control(["0", "--project"])` and `#show culprit/1.` to enumerate distinct culprits.

**Docker and pgvector in a Claude Code cloud session. Unproven.** This plan was written on Windows and could not open a cloud session. The existing `scripts/install_pkgs.sh` already runs `service postgresql start`, which suggests native PostgreSQL. The plan assumes no Docker in lanes and gates the compose path in the `compose-smoke` CI job and the operator's fresh-machine check. P0-1's first build box probes this and records the result.

**How planned lies enter the solver. Unproven.** The spec says lies are verified "as testimony" but does not say how testimony constrains culprits. The plan's starting point is that a `claims/2` atom never counts as a fact. The architect step in P1-2 settles this and ADR 001 records it.

## Appendix B. Alternatives rejected

**Closed-world ASP encoding.** It loses the counterexample for dropped clues, as Appendix A shows.

**One PR per phase.** The operator's plan allows one branch per phase. A single PR for Phase 2 or Phase 3 would carry three to four separable changes with no evidence of its own, so each phase splits into stacked PRs, each on its own `phase-<n>/<slug>` branch.

**Ten live lanes per PR.** The bundled playbook asks for ten. The operator capped live verification at two, so each PR keeps the regression lane and one load-bearing scenario. Most PRs here add one behavior, and the unit block covers the edge cases.

**Autopilot-full.** It hands merge authority to owners. `CLAUDE.md` forbids agents from merging, and every phase waits on the operator, so the plan uses Autopilot-stack.

**Docker Compose inside lanes.** Lanes boot native PostgreSQL and `uvicorn` directly, because Docker in cloud sessions is unproven. Compose stays the operator's local path and has its own CI job.

**Stream the draft while verifying.** The spec defers verify-while-streaming. P3-3 streams only a reply the verifier already passed.

**A LiteLLM proxy for PydanticAI.** A proxy adds a service to every environment. A PydanticAI model adapter over `app.llm.complete` keeps one choke point with no extra process.

## Appendix C. Risks

**Model keys and network in cloud sessions.** Every live lane needs the `mendacia` environment's secrets and an allowlist that reaches the providers. Lands in P0-2. The owner watches the first `make doctor` and stops with a `docs/QUESTIONS.md` entry if a host is blocked.

**No embedding model from Anthropic.** `MODEL_EMBED` needs a second provider. Lands in P3-2. The operator's choice also fixes `EMBED_DIM`, and changing it later means a new migration and a reindex.

**PydanticAI routed through the wrapper.** A custom `Model` adapter depends on PydanticAI internals that change between releases. Lands in P2-2. The owner pins the version and keeps the adapter tested in replay.

**Replay keys drift.** Any prompt edit changes the SHA-256 key and breaks replay tests with `MissingRecording`. Lands in P0-2 and every later PR. The owner rerecords with `LLM_MODE=record` in the same PR and the error message names the key.

**Lies the evidence cannot expose.** The spec lets a suspect admit a hidden fact once confronted, but no rule forces a case to contain the exposing clue. Lands in P1-2. The default is a solver warning, not a failure. The owner writes the question to `docs/QUESTIONS.md` so the operator can promote it to a check.

**Budgets are first guesses.** Every perf number in this plan is an initial budget, not a measurement. Lands in every PR. An owner whose run misses a budget for a reason the code cannot fix writes the measured number to `docs/QUESTIONS.md` instead of loosening the rule.

**Eval cost.** `make eval N=100` runs a strong-model bot for 100 games. Lands in P5-2. The N=5 projection decides whether the run starts.

**promptfoo over WebSocket.** The jailbreak set targets the same WebSocket endpoint as players. Lands in P5-2. If the promptfoo WebSocket provider cannot read the streamed `done` message, the owner adds a thin HTTP wrapper in `evals/` and records why.

**No browser driver skill before P3-4.** Lanes before P3-4 drive the CLI and the API through the `run` skill. P3-4 creates `.claude/skills/verify/SKILL.md`, and later lanes depend on it.

## Appendix D. Links and reading list

- `docs/spec.md` for features and data shapes. Read it before every PR.
- `CLAUDE.md` for the project rules and commands.
- `docs/adr/` for each decision as it lands.
- PRs that get `skills/how/SKILL.md` before editing are P2-2, P3-3, and P4-1, because each builds on code from an earlier phase.
- PRs that get `skills/interrogate/SKILL.md` before code-ready are P1-2, P2-1, P2-2, P3-2, and P4-1.
- Every owner keeps a decision trail per `skills/show-me-your-work/SKILL.md` at `.audit/<pr-id>.tsv`. The root commits its program trail at the close.
