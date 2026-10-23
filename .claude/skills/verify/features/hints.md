# Hints

The player spends one of three hints. The hint names something the player can already see, usually an unopened key document.

## Sub-features

- `take`: `Take a hint` adds the hint text to the `Hints` region.
- `budget`: "3 hints left" falls by one per hint. The button is disabled at 0.

## How to get to it (user POV)

- The `Hints` region in the left column, or the Case tab on a phone.

## Driving it with Playwright

Preconditions: baseline, a game started with `start("manor")`.

- Take: `await d.hint()` returns text that contains "pavilion", and the `Case` region shows "2 hints left".
- Exhaust: call `d.hint()` three times. The fourth click is impossible because the button is disabled.

## Gotchas

- Hints are kept in the tab's journal. A new tab shows the budget but not the earlier hint texts.
