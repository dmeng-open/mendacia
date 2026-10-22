# Open questions

## `docs/spec.md` is missing from `main`

`docs/plan.md` and P0-1 say `main` holds `docs/spec.md` and that `README.md` lists "the six local commands from `docs/spec.md`". The file is not on `main`. P0-1 lists these six, taken from the Makefile targets it adds: `make setup`, `make up`, `make db-create migrate`, `make api`, `make test`, `make ci`. Confirm the intended six or push `docs/spec.md`, and the README follows it.

## Should an unexposable lie fail the solver check?

`docs/plan.md` Appendix C says no rule forces a case to contain a clue that exposes a planned lie. P1-2 reports it as a warning: `make check-case` prints `lies WARN` and `<lie>: no clue exposes it`, and the case still passes. A lie whose claim the case's own facts allow prints `<lie>: the case facts allow the claim to be true`, also as a warning. Promote either warning to a failure, or keep both as warnings.
