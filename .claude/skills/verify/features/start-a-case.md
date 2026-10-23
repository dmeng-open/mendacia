# Start a case

The player opens the site, picks one of three cases, and lands on the game page with the case summary, the suspects, and the budget loaded.

## Sub-features

- `list`: `/` lists Play Gallery, Play Lighthouse, and Play Manor.
- `auto-start`: `/?case=<id>` creates a game and redirects to `/play/<gameId>`.
- `layout`: three columns at 768 px and wider; Case, Chat, and Archive tabs below.
- `denied`: a game URL opened in another browser shows "This game belongs to another browser session."

## How to get to it (user POV)

- Open `http://localhost:$WEB_PORT/` and click a case.
- Run `make play CASE=gallery`, which prints and opens `http://localhost:$WEB_PORT/?case=gallery`.

## Driving it with Playwright

Preconditions: baseline.

- Auto-start: `await detective(page).start("manor")`. The URL matches `/play/<id>` and the `Case` region shows the heading "Death at Ashcombe Manor".
- Budget: the `Case` region shows "20 questions left" and "3 hints left".
- Phone layout: run with `--project phone`. The tablist `Panels` is visible, and `detective.show("Archive")` reveals the `Documents` region.
- Denied: open the `/play/<id>` URL in a fresh browser context. The page shows the denied heading and a "Start a new game" link.

## Gotchas

- Every visit to `/?case=` creates a new game. Reload `/play/<id>` instead to keep one.
- The chat journal lives in `sessionStorage`, so a new tab shows an empty transcript for the same game.
