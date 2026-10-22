# Open questions

## `docs/spec.md` is missing from `main`

`docs/plan.md` and P0-1 say `main` holds `docs/spec.md` and that `README.md` lists "the six local commands from `docs/spec.md`". The file is not on `main`. P0-1 lists these six, taken from the Makefile targets it adds: `make setup`, `make up`, `make db-create migrate`, `make api`, `make test`, `make ci`. Confirm the intended six or push `docs/spec.md`, and the README follows it.
