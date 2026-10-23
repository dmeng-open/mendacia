# Search and read the archive

The player searches the evidence archive, sees hits with the matching words highlighted, and opens documents. Unopened documents show as sealed. Documents the player has not unlocked are not listed at all.

## Sub-features

- `search`: the `Search the archive` searchbox lists hits in the `Search results` list.
- `highlight`: each hit shows a passage with matches inside `<mark>`.
- `sealed`: an unopened document has a lock icon labelled "Sealed" and an `Open <title>` button.
- `read`: opening shows a dialog with the title, source, and body. An opened document then offers `Read <title>`.
- `unlock`: opening a key document or earning a clue can add documents to the list.

## How to get to it (user POV)

- The right column on desktop, or the Archive tab on a phone.

## Driving it with Playwright

Preconditions: baseline, a game started with `start("manor")`.

- Search: `await d.search("empty velvet case in the dressing table")`. `titles[0]` is "Housekeeper's note on the letter opener case" and `marks` is above 0.
- Read: `await d.open("Garden pavilion visitors' book")` returns a body that contains "Dr. A. Finch", and the `Clues` region gains the pavilion clue.
- Unlock (gallery): `start("gallery")`, then `visibleDocuments()` lacks "East hall camera log" until `open("Security desk memo")`.

## Gotchas

- Replay mode answers only searches whose query embedding is recorded. Use queries from `backend/evals/retrieval_queries.yaml`.
- A search hit and a document row can both have an `Open <title>` button. Scope to the `Documents` region or the `Search results` list.
