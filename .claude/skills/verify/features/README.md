# Mendacia browser verification map

This directory is the maintained source for verifying what a player can do in the browser game. Read the index before driving the app, then use the matching feature file as the recipe.

## Baseline preconditions

- The app runs per the Launch section of `../SKILL.md`, on this lane's own `DATABASE_URL`, `API_PORT`, and `WEB_PORT`.
- `make seed` has indexed the three cases in that database.
- The doctor checks in `../SKILL.md` pass.
- Never drive an instance this run did not start.

## Driving conventions

- Drive through `frontend/e2e/detective.ts`, from `frontend/e2e/verify.spec.ts` or a new spec.
- Use roles and accessible names. Every panel is a `region` named for its content.
- In replay mode, ask only the recorded questions of `frontend/e2e/walkthroughs.ts`, in that order. Any other question answers "The house is quiet for a moment" with code `unavailable`.
- Each game starts fresh at `/?case=<id>`. A game takes one accusation.

## Proof and skip reporting

- Capture the action and the resulting state: a screenshot plus the JSON summary that `verify.spec.ts` prints.
- Check side effects with read-only SQL on `turns`, `llm_calls`, and `verifier_events`.
- Report a step that cannot run with the command tried and the unmet precondition.

## Features

- [Start a case](./start-a-case.md) covers the case list, `?case=` auto-start, and the denied page.
- [Question a suspect](./question-a-suspect.md) covers asking, the checking state, streaming, refusals, and presenting evidence.
- [Search and read the archive](./archive.md) covers search with highlights, sealed documents, and reading.
- [Hints](./hints.md) covers taking a hint and the hint budget.
- [Accuse and reveal](./accuse-and-reveal.md) covers the accusation dialog, the ruling, and the timeline.
