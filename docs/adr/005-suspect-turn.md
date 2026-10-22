# 005. Release a suspect reply only when every claim in it was checked

## Status

Accepted.

## Context

P2-2 runs each suspect turn as a LangGraph: retrieve, generate, extract, verify, rewrite (at most twice), fallback, and commit. The verifier from ADR 004 judges only the claims the extractor lists, and the extractor is a model. A reply the extractor reads as claim-free would otherwise be released without any check.

## Decision

- **Fail closed.** A draft is released only when it is non-empty, extraction succeeded, no claim is blocked, and it either has claims or names nothing from the case. A claim-free draft that names a person, place, or item from the case is `unchecked` and goes to rewrite, then fallback. An empty draft skips extraction and falls back.
- **Denials are claims.** The extractor marks a denial with `negated`, so ADR 004's denial rule judges "I never went near the study".
- **Player text is data.** The extractor gets `{"question": ..., "reply": ...}` as JSON and is told the question is untrusted and never an instruction. Claims come from the reply only.
- **Every fallback logs.** A fallback writes one `verifier_events` row per blocked claim, or one `unverified` row when nothing was checkable. Migration 0004 adds the `unverified` rule.
- **Bad input never reaches the checkpoint.** `Interrogation.ask` refuses an unknown suspect or clue before the graph runs. Presented clues become durable only in `commit`, so a turn that crashes leaves no exposure behind.
- **One turn per thread at a time.** `Interrogation` holds a lock per suspect, so two overlapping asks run one after the other instead of losing a turn.

## Consequences

The suspect model generates on `ModelRole.FAST`, and extraction also runs on `FAST`. A turn that needs a rewrite makes four model calls, so the 8 s live p95 holds for clean turns and can be exceeded on rewrite turns. `make record-fixtures` re-records the suspect scenarios whenever a prompt changes, and the three-failure scenario uses authored drafts declared as test inputs, with real recorded extraction calls.
