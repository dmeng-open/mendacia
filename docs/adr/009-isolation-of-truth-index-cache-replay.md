# 009. Keep Truth out of the index, and key every cache by case version and visibility

## Status

Accepted. This is P3-4, ADR-S04 of the v2.1 security plan.

## Context

P3-3 gave each document a visibility, so a player holds a growing subset of the archive. Search is the first path where a player's free text meets all of the archive at once. A vector index and a full-text index answer by similarity, not by permission, so a locked document that matches the words ranks like any other. Three other stores sit beside the index and can leak the same way: the embedding replay files, any result cache, and the audit log.

## Decision

**The index holds player-layer text only.** `evidence_chunks` stores, per chunk, `case_version`, `document_id`, `ordinal`, `case_id`, `title`, `source`, `unlocked_by`, `text`, `embedding`, `text_sha`, and a generated `tsvector`. It has no `is_key`, no clue, fact, secret, culprit, or solution chain. A chunk is copied from `EvidenceDoc.title`, `source`, `body`, and `visibility` and from nothing else, so a Truth-layer value has no column to land in. `unlocked_by` is kept for display and audit. It names the clue or document that opens the row, and no search result returns it.

**One key per row, and replacement by case version.** A row is keyed by `(case_version, document_id, ordinal)`. `case_version` hashes the whole case (ADR 007), so rows under one version describe exactly one set of documents, and editing a case creates new rows beside the old ones. A game in progress keeps searching the version it started on. `text_sha` is the SHA-256 of the embed text, `CHUNKER_VERSION`, and the embed model. `index_case` embeds a document only when its chunks are missing or their `text_sha` differs, embeds before it opens the transaction, then upserts and removes rows whose `(document_id, ordinal)` is gone under an advisory lock on the case version. A rerun on an unchanged case makes no embed call and leaves the same rows.

**Two gates on every query, from two sources.** The SQL filter is `case_version = :cv and document_id = any(:visible)`. `PlayerScope.of` computes `visible` from `engine.evidence.visible_documents(case, discovered, opened)`, and refuses a subject that is not a player or a case that is not the subject's. The second gate is `authorize(subject, "open_document", ...)` built from the in-memory `Case`, never from the row. A hit that passes the first gate and fails the second is dropped and logged as `search_evidence` with decision `deny` and reason `acl_leak:<reason>`. The row holds the document id in the trace, never the query or the chunk text. Search adds no row to the policy table: it reuses the player `open_document` row, so a document is searchable exactly when it is openable.

**Cache keys.** The index is the only cache this PR adds, and its key is above. An embedding replay file (ADR 003) is keyed by the role and the input texts. That is safe because a vector is a pure function of its text, and the text is a document body or a player-authored query, never Truth. Replay files hold the text of locked documents too. They are test inputs and are never served to a player. Search results are not cached. A result cache added later must key on `case_version`, a hash of the sorted visible document ids, and the normalized query. A key without the visible set would serve one player's unlocked hits to another.

**Query boundary.** `normalize_query` strips, collapses whitespace, and caps the query at 500 characters. An empty query returns nothing. The full-text query joins the words with OR, so a natural-language question matches on any term, and ranking decides the order. Highlights use `[[` and `]]` markers, never HTML, so a document body cannot inject markup into a page.

**Fusion.** The vector and full-text top 20 come back from one SQL round trip. `fuse` merges them by reciprocal rank at `k=60` per document: a document scores from its best chunk in each list, and ties break by best single rank, then document id, so the order is total. There is no ANN index. A case has about 20 chunks, an exact scan costs a few milliseconds, and a filtered ANN scan can return fewer than 20 rows after the visibility filter.

**Eval.** `make retrieval-eval` derives each query's label from `visible_documents`. Recall@10 and MRR count found queries. A withheld query passes when its locked target is absent from the results. ACL leaks count returned documents outside `visible_documents`, a check independent of `authorize`. The run exits 1 on any leak or any returned locked target. The loader rejects unknown ids and a case with fewer than two withheld queries. The report gives p95 with and without the query-embedding call, because the embedding call dominates it.

## Rejected

**Filtering in `authorize` alone.** It would rank locked documents and discard them after, so a page of ten could shrink to two, and a bug in the discard would leak. The SQL filter keeps them out of the candidate lists.

**Filtering on the stored `unlocked_by` alone.** The row is a copy made at index time. The scope built from the live case is the source of truth, and `authorize` re-checks against it.

**A `pgvector` Python adapter.** The vector is bound as text and cast in SQL, so the project gains no dependency.

**Caching search results per player.** Search costs one embedding call and one query. A cache keyed wrongly leaks, and a cache keyed rightly saves little.

## Consequences

- Changing `EMBED_DIM` needs a new migration, because the column is `vector(EMBED_DIM)`.
- Old case versions stay in the table until a cleanup removes them. No query reads them without asking for their version.
- Changing `embed_text` or the chunker requires bumping `CHUNKER_VERSION`, or a reindex will skip the stale rows.
- P3-5 calls the retriever through `asyncio.to_thread` and passes the subject for the game. A route that builds a `PlayerScope` by hand skips the first gate, and the second gate still holds.
- `make seed` and `make retrieval-eval` replay by default. `RECORD=1` records missing embeddings, and `make record-retrieval` runs both that way.
