import json
import math
import os
import uuid
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

import pytest
import sqlalchemy as sa

from agents.game_master import GameState
from app.config import Settings
from engine.schema import Case, EvidenceDoc
from evidence import AuthorizedRetriever, PlayerScope, index_case
from evidence.chunk import MAX_TOKENS, approx_tokens, chunk_document
from evidence.search import CaseMismatch, NotAPlayer, Ranked, fuse
from security.context import AuthContext, case_version

CASES = Path(__file__).resolve().parents[3] / "cases"
MANOR = json.loads((CASES / "manor.json").read_text())
ENGINE = sa.create_engine(os.environ["DATABASE_URL"])
DIM = Settings().embed_dim
FAR = math.pi / 2


def vec(angle: float) -> list[float]:
    v = [0.0] * DIM
    v[0], v[1] = math.cos(angle), math.sin(angle)
    return v


def variant(tag: str, fillers: int = 0, edit: dict[str, dict[str, str]] | None = None) -> Case:
    data = json.loads(json.dumps(MANOR))
    data["title"] = f"{MANOR['title']} ({tag})"
    for doc in data["documents"]:
        doc.update((edit or {}).get(doc["id"], {}))
    data["documents"] += [
        {
            "id": f"filler_{i}",
            "title": f"Filler memo {i}",
            "source": "memo",
            "body": "Lamps were trimmed and the silver was counted before supper.",
            "is_key": False,
            "visibility": "open",
        }
        for i in range(fillers)
    ]
    return Case.model_validate(data)


class Embedder:
    def __init__(self, case: Case, angles: dict[str, float]) -> None:
        self.titles = {d.title: angles.get(d.id, FAR) for d in case.documents}
        self.batches = 0

    def batch(self, texts: list[str]) -> list[list[float]]:
        self.batches += 1
        return [vec(self.titles[t.split("\n", 1)[0]]) for t in texts]

    def query(self, text: str) -> list[float]:
        return vec(0.0)


def scope(
    case: Case, discovered: tuple[str, ...] = (), opened: tuple[str, ...] = ()
) -> PlayerScope:
    game = uuid.uuid4().hex
    state = GameState(case_id=case.id, game_id=game, discovered=discovered, opened=opened)
    subject = AuthContext(game, "player", game, case_version(case), 0)
    return PlayerScope.of(subject, case, state)


def count(case: Case) -> int:
    with ENGINE.connect() as conn:
        return int(
            conn.scalar(
                sa.text("select count(*) from evidence_chunks where case_version = :cv"),
                {"cv": case_version(case)},
            )
            or 0
        )


def security_rows(game: str) -> list[Any]:
    with ENGINE.connect() as conn:
        return list(
            conn.execute(
                sa.text(
                    "select action, decision, reason_code, decision_trace::text "
                    "from security_events where game_id = :g"
                ),
                {"g": game},
            )
        )


@pytest.fixture
def indexed() -> Iterator[Any]:
    versions: list[str] = []

    def build(case: Case, angles: dict[str, float]) -> AuthorizedRetriever:
        embedder = Embedder(case, angles)
        index_case(case, ENGINE, embedder.batch)
        versions.append(case_version(case))
        return AuthorizedRetriever(ENGINE, embedder.query)

    yield build
    with ENGINE.begin() as conn:
        conn.execute(
            sa.text("delete from evidence_chunks where case_version = any(:v)"), {"v": versions}
        )


def ranked(retriever: Literal["vector", "text"], rank: int, doc: str) -> Ranked:
    return Ranked(retriever, rank, doc, doc, "memo", (), "")


def test_rrf_merges_two_lists_in_a_known_order() -> None:
    rows = [
        ranked("vector", 1, "a"),
        ranked("vector", 2, "b"),
        ranked("vector", 3, "d"),
        ranked("text", 1, "c"),
        ranked("text", 2, "d"),
        ranked("text", 3, "a"),
    ]
    hits = fuse(rows)
    assert [h.document_id for h in hits] == ["a", "d", "c", "b"]
    assert hits[0].score == pytest.approx(1 / 61 + 1 / 63)
    assert (hits[0].vector_rank, hits[0].text_rank) == (1, 3)
    assert (hits[3].vector_rank, hits[3].text_rank) == (2, None)


def test_rrf_scores_a_document_once_by_its_best_chunk() -> None:
    hits = fuse([ranked("vector", 1, "a"), ranked("vector", 2, "a"), ranked("vector", 3, "b")])
    assert [(h.document_id, h.vector_rank) for h in hits] == [("a", 1), ("b", 3)]


def test_rrf_ties_break_by_best_rank_then_document_id() -> None:
    hits = fuse([ranked("text", 1, "y"), ranked("vector", 1, "x"), ranked("vector", 2, "z")])
    assert [h.document_id for h in hits] == ["x", "y", "z"]


def test_hybrid_search_merges_vector_and_text_hits(indexed: Any) -> None:
    case = variant("merge")
    retriever = indexed(case, {"barometer_note": 0.0, "ashcombe_ledger": 0.2, "dinner_menu": 0.3})
    hits = retriever.search(scope(case), "Michaelmas loan")
    top = hits[:3]
    assert [h.document_id for h in top] == ["ashcombe_ledger", "barometer_note", "dinner_menu"]
    assert (top[0].vector_rank, top[0].text_rank) == (2, 1)
    assert (top[1].vector_rank, top[1].text_rank) == (1, None)
    assert "[[Michaelmas]]" in top[0].highlight


def test_keyword_only_hit(indexed: Any) -> None:
    case = variant("keyword", fillers=22)
    angles = {f"filler_{i}": 0.1 + 0.01 * i for i in range(22)}
    hits = indexed(case, angles).search(scope(case), "barometer glass falling")
    barometer = next(h for h in hits if h.document_id == "barometer_note")
    assert barometer.vector_rank is None
    assert barometer.text_rank == 1


def test_vector_only_hit(indexed: Any) -> None:
    case = variant("vector")
    hits = indexed(case, {"dinner_menu": 0.0}).search(scope(case), "zzqx unmatched words")
    assert hits[0].document_id == "dinner_menu"
    assert all(h.text_rank is None for h in hits)


def test_locked_document_is_never_returned_until_unlocked(indexed: Any) -> None:
    case = variant("locked")
    retriever = indexed(case, {"solicitor_letter": 0.0})
    query = "revised will residue Cottage Hospital"
    locked = retriever.search(scope(case), query)
    assert "solicitor_letter" not in {h.document_id for h in locked}
    unlocked = retriever.search(scope(case, discovered=("diary_page",)), query)
    assert unlocked[0].document_id == "solicitor_letter"
    assert unlocked[0].visibility == "unlocked"


def test_a_hit_from_another_case_version_is_filtered_out(indexed: Any) -> None:
    mine = variant("mine")
    other = variant(
        "other", edit={"barometer_note": {"title": "Zeppelin sighting", "body": "A zeppelin."}}
    )
    retriever = indexed(mine, {})
    indexed(other, {"barometer_note": 0.0})
    seen = retriever.search(scope(mine), "zeppelin")
    assert not any("zeppelin" in (h.title + h.highlight).lower() for h in seen)
    assert any(h.title == "Zeppelin sighting" for h in retriever.search(scope(other), "zeppelin"))


def test_index_rerun_keeps_rows_and_pays_for_nothing(indexed: Any) -> None:
    case = variant("rerun")
    embedder = Embedder(case, {})
    first = index_case(case, ENGINE, embedder.batch)
    rows = count(case)
    again = index_case(case, ENGINE, embedder.batch)
    try:
        assert (first.embedded_documents, again.embedded_documents) == (len(case.documents), 0)
        assert embedder.batches == len(case.documents)
        assert count(case) == rows == first.chunks == again.chunks
    finally:
        with ENGINE.begin() as conn:
            conn.execute(
                sa.text("delete from evidence_chunks where case_version = :cv"),
                {"cv": case_version(case)},
            )


def test_index_drops_rows_whose_chunk_no_longer_exists(indexed: Any) -> None:
    case = variant("stale")
    indexed(case, {})
    with ENGINE.begin() as conn:
        conn.execute(
            sa.text(
                "insert into evidence_chunks select case_version, 'gone', 0, case_id, title, "
                "source, unlocked_by, text, embedding, text_sha from evidence_chunks "
                "where case_version = :cv and ordinal = 0 and document_id = 'dinner_menu'"
            ),
            {"cv": case_version(case)},
        )
    rows = count(case)
    index_case(case, ENGINE, Embedder(case, {}).batch)
    assert count(case) == rows - 1


def test_authorize_recheck_drops_and_logs_a_forged_row(indexed: Any) -> None:
    case = variant("forged")
    retriever = indexed(case, {"solicitor_letter": 0.0})
    with ENGINE.begin() as conn:
        conn.execute(
            sa.text(
                "update evidence_chunks set unlocked_by = '{}' "
                "where case_version = :cv and document_id = 'solicitor_letter'"
            ),
            {"cv": case_version(case)},
        )
    query = "revised will residue Cottage Hospital"
    honest = scope(case)
    assert "solicitor_letter" not in {h.document_id for h in retriever.search(honest, query)}
    assert security_rows(honest.subject.game_id) == []

    faulty = replace(honest, visible=honest.visible | {"solicitor_letter"})
    assert "solicitor_letter" not in {h.document_id for h in retriever.search(faulty, query)}
    [row] = security_rows(honest.subject.game_id)
    assert row[:3] == ("search_evidence", "deny", "acl_leak:locked")
    assert "solicitor_letter" in row[3]
    assert "Cottage Hospital" not in row[3]


def test_player_scope_checks_its_boundary() -> None:
    case = variant("scope")
    game = uuid.uuid4().hex
    state = GameState(case_id=case.id, game_id=game)
    with pytest.raises(NotAPlayer):
        PlayerScope.of(AuthContext(game, "suspect", game, case_version(case), 0), case, state)
    with pytest.raises(CaseMismatch):
        PlayerScope.of(AuthContext(game, "player", game, "other", 0), case, state)


def test_blank_query_returns_nothing() -> None:
    case = variant("blank")
    assert AuthorizedRetriever(ENGINE, Embedder(case, {}).query).search(scope(case), "  \n ") == []


def test_long_paragraph_is_split_under_the_cap() -> None:
    sentence = "The tide turned at ten and the lamp burned low. "
    doc = EvidenceDoc(
        id="long", title="Long", source="memo", body=sentence * 400, is_key=False, visibility="open"
    )
    chunks = chunk_document(doc)
    assert len(chunks) > 1
    assert all(approx_tokens(c.text) <= MAX_TOKENS for c in chunks)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
