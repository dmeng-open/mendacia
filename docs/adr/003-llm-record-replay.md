# 003. Record and replay model calls in the wrapper

## Status

Accepted.

## Context

Mendacia calls language models for suspect turns, case generation, verification, and embeddings. `make ci` and the unit tests must never call a real model, but they must still exercise the code paths that do. Every real call must also be measured for tokens, cost, and latency, so a lane or an eval can prove it stayed under budget.

## Decision

Every model call goes through `app.llm.complete` or `app.llm.embed`. No other module imports `litellm`, and no source file names a model. Code asks for a role (`FAST`, `STRONG`, `EMBED`), and `Settings` resolves the role to `MODEL_FAST`, `MODEL_STRONG`, or `MODEL_EMBED`. `tests/test_llm_boundary.py` enforces both rules.

`LLM_MODE` selects one of three modes.

- `live` calls the provider.
- `record` calls the provider and saves the result to `backend/tests/fixtures/llm/<key>.json`.
- `replay` reads that file and never opens a network connection or reads a provider key. A missing file raises `MissingRecording`, which names the key.

The key is the SHA-256 of a canonical JSON object that holds the role, the messages, and the call parameters (`max_tokens`, the `response_format` JSON schema, or the embedding input). The key leaves out the model name, so a change to `MODEL_FAST` does not invalidate the recordings. A change to a prompt or a parameter does, and the test that depends on it fails with the key it needs.

Every call in every mode writes one `llm_calls` row with the model, role, purpose, game id, prompt and completion tokens, `cost_usd` from the LiteLLM cost table, `latency_ms`, and the mode. A replay row carries the recorded usage, so a test can assert accounting without a network call. Budget checks sum `cost_usd` only over `mode <> 'replay'` rows, because replay spends nothing.

Replay lives in the wrapper, not in a mock or an HTTP cassette layer, for three reasons.

- One place owns the key scheme, the accounting row, and the mode switch, so tests run the same code path that production runs.
- The key is computed from the request the wrapper builds, not from provider-specific HTTP bodies, so it does not change when LiteLLM changes its wire format or when the provider changes.
- A test that forgets to record fails loudly with `MissingRecording` instead of reaching the network.

The provider key is read from `MENDACIA_ANTHROPIC_API_KEY` and passed to LiteLLM as `api_key`, not read from `ANTHROPIC_API_KEY`, so the game's key never reaches other tools in the same environment.

## Consequences

Tests set `LLM_MODE=replay` in `tests/conftest.py`. Tests that need a real model carry `@pytest.mark.live` and run only with `pytest -m live`. Adding a prompt to a replayed test means running it once with `LLM_MODE=record` and committing the new file. `make doctor` checks the settings, the database, and one `FAST` call with `max_tokens=1`, and `make doctor SKIP_MODEL=1` runs in CI without a key.

## Amendment: record only what is missing (P2-2)

`LLM_MODE=record` now replays a request whose fixture already exists and calls the provider only for a missing key. A multi-turn scenario repeats earlier turns' requests, and overwriting those files with a fresh model output would break the next turn's recorded request. Re-recording a fixture means deleting its file first. `make record-fixtures [SCENARIO=<name>]` drives the suspect scenarios in `backend/tests/agents/suspect_scenarios.py` with real model calls, outside pytest, and keeps a run only when its outcome matches the scenario.
