# Accuse and reveal

The player names a culprit, cites discovered clues, and sees the ruling, the clues they cited, how many solution-chain clues they cited, and the true timeline.

## Sub-features

- `dialog`: `Accuse` opens a dialog with one radio per suspect and one checkbox per discovered clue.
- `ruling`: the `Ruling` region shows "Correct." or "Wrong. That suspect did not do it."
- `cited`: "You accused <name>", the cited clue texts, and "You cited N of the M clues in the solution chain."
- `timeline`: the `Timeline` region lists the true events in order.
- `once`: after the accusation the Archive shows `See the reveal` instead of `Accuse`.

## How to get to it (user POV)

- The `Accuse` button at the bottom of the right column, or the Archive tab on a phone.

## Driving it with Playwright

Preconditions: a game played through the manor walkthrough up to its accusation, so three clues are discovered.

- Accuse: `await d.accuse("Clara Ashcombe", "all")` returns "Correct." and the URL ends in `/reveal`.
- Timeline: the `Timeline` region has a heading "Timeline" and at least one list item.
- Cited: the page shows "You cited 3 of the 3 clues in the solution chain."

## Gotchas

- Before the accusation `/play/<id>/reveal` redirects back to the game.
- The reveal names suspects only through the journal of the tab that accused. Another tab shows the ruling and timeline without "You accused".
