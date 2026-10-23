# Open questions for the operator

## P3-4: the 300 ms search p95 budget cannot hold with a live query embedding

The plan's P3-4 perf rule fails when search p95 exceeds 300 ms. With `LLM_MODE=live`, the retrieval
eval measured p95 305 ms overall (gallery 308 ms, lighthouse 259 ms, manor 275 ms). The same
searches without the query embedding have p95 6.1 ms. The embedding call to
`openai/text-embedding-3-small` is the limiter: a raw keep-alive HTTP probe from the cloud container
to the OpenAI embeddings endpoint measured median 213 ms and p95 324 ms over 15 calls, so no search
code can bring the total under 300 ms on this network.

Default taken: the code ships as is. The report prints p95 with and without the embed, so both
numbers stay visible. Options for the operator:

1. Judge the 300 ms budget on search time excluding the query embedding (6.1 ms), and set a separate
   budget for the embedding round trip.
2. Raise the budget to cover the provider round trip (for example 500 ms).
3. Cache query embeddings by model and normalized query text (ADR 009 allows this key). Repeat
   queries then skip the round trip, but a first query still pays it.

## P3-5: the pre-reveal scan forbids the culprit id, but the game view lists suspects by id

The plan's P3-5 unit test scans every response body before the reveal for the culprit id. `GET /games/{id}` must list the suspects so the player can choose whom to question, and the culprit is one of them. Listing suspects by their case ids would put the culprit id in every view. The same holds for discovered `solution_chain` clue ids in the clue list.

Default taken: over HTTP every suspect id and clue id is a per-game handle, `h_` plus the first 10 hex digits of HMAC(`SESSION_SECRET`, `game_id:id`), and requests map handles back on the server (ADR 011). Document ids stay raw. The CLI keeps raw ids so the trunk replay scripts run unchanged. The scan in `tests/api/test_games.py` passes with no exclusions. Options for the operator:

1. Keep handles (the default).
2. Exempt the suspect roster from the scan and send raw suspect ids, keeping handles for clues only.

## P3-5: the 200k token cap is a hard stop for the rest of the game

The plan says that after 200k tokens in one game the session gets a 60 s cooldown. The token count is cumulative, so it never falls back under the cap, and a 60 s cooldown would start again on the next call.

Default taken: once a game's `llm_calls` rows sum to 200,000 tokens, `ask_question` and `confront_evidence` answer `cooldown` for the rest of the game. Documents, hints, search, and the accusation stay available, and no question is spent (ADR 011). The replayed manor game in `tests/api/test_games.py` used 4,357 tokens for its two questions (summed from `llm_calls`), so a fair 20-question game stays well below the cap. Options for the operator:

1. Keep the hard stop (the default).
2. Count tokens in a sliding window (for example 200k per 10 minutes) so the cooldown can lift.

## P3-5: live time to `done` p95 is bound by the three-draft rewrite path

The plan's P3-5 perf rule fails when live time to `done` p95 exceeds 8 s. Ten live asks over the WebSocket measured median 3.8 s and p95 8.9 s (n=10, so p95 is the slowest ask). The two slowest asks, 8.9 s and 7.9 s, each ran the P2-2 rewrite loop to its limit: three drafts, so six sequential model calls of 0.7 to 2.6 s each. The eight asks with one draft took 2.2 to 6.3 s. Guard latency (`authorize`, the broker, and verification, summed from `security_events`) had p95 18.5 ms, so the HTTP layer adds almost nothing.

Default taken: the code ships as is. Options for the operator:

1. Judge the 8 s budget on turns that release a first draft, and track rewrite turns separately.
2. Raise the budget to cover a full rewrite loop (for example 12 s).
3. Cut the loop: fewer drafts, a faster extractor model, or fall back after one rewrite.

## P3-6: "locked documents shown as locked" would leak how many documents are still hidden

The plan asks `ArchivePanel.tsx` to show locked documents as locked. The game view lists only visible documents; a locked document never reaches the browser (ADR 008). Listing locked documents, even as blank placeholders, would tell the player how many documents the case still hides, which is the kind of hidden statistic open decision 5 rules out before the reveal.

Default taken: visible documents the player has not opened render as sealed, with a lock icon and an "Open" button. Locked documents render nothing, and the UI shows no document count. Options for the operator:

1. Keep sealed-but-visible documents only (the default).
2. Show a fixed line such as "Some records are still out of reach" whether or not any are locked, which tells the player nothing about the count.
3. Add locked documents to the view as placeholders and accept the count leak.

## P3-6: the reveal has raw ids and no names or clue text

`GET /games/{id}/reveal` returns the culprit, the accused, and the chain as raw case ids, while the game view used per-game handles and never sent raw ids. The browser cannot map the reveal back to names or clue descriptions, and showing raw ids such as `pike_kitchen_testimony` would look broken.

Default taken: the reveal page shows the ruling text, "You accused <name>" and the cited clue descriptions from the tab's own journal (kept when the player accused), "You cited N of the M clues in the solution chain", and the timeline. It never renders a raw id. A wrong accusation therefore does not name the true culprit beyond what the timeline says. Options for the operator:

1. Keep the journal-based reveal (the default).
2. Add the culprit's name, the accused's name, and the chain clue descriptions to `Reveal` in a backend follow-up, which also lets another tab or device show the full reveal.
