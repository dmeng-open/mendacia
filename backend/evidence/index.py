import hashlib
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path

import sqlalchemy as sa

from app import llm
from app.config import Settings
from app.db import sync_engine
from engine.schema import Case, Id
from evidence.chunk import CHUNKER_VERSION, Chunk, chunk_document
from security.context import case_version

BatchEmbed = Callable[[list[str]], list[list[float]]]

EXISTING = sa.text(
    "select document_id, ordinal, text_sha from evidence_chunks where case_version = :cv"
)
UPSERT = sa.text("""
insert into evidence_chunks
    (case_version, document_id, ordinal, case_id, title, source, unlocked_by, text,
     embedding, text_sha)
values
    (:cv, :document_id, :ordinal, :case_id, :title, :source, :unlocked_by, :text,
     CAST(:embedding AS vector), :text_sha)
on conflict (case_version, document_id, ordinal) do update set
    case_id = excluded.case_id, title = excluded.title, source = excluded.source,
    unlocked_by = excluded.unlocked_by, text = excluded.text,
    embedding = excluded.embedding, text_sha = excluded.text_sha
""")
DELETE = sa.text(
    "delete from evidence_chunks "
    "where case_version = :cv and document_id = :document_id and ordinal = :ordinal"
)


@dataclass(frozen=True)
class IndexReport:
    case_id: Id
    case_version: str
    chunks: int
    embedded_documents: int


def default_embed_batch(texts: list[str]) -> list[list[float]]:
    return llm.embed(texts, purpose="index_case").vectors


def embed_text(chunk: Chunk) -> str:
    return f"{chunk.title}\n\n{chunk.text}"


def text_sha(chunk: Chunk, embed_model: str) -> str:
    return hashlib.sha256(
        f"{embed_text(chunk)}|{CHUNKER_VERSION}|{embed_model}".encode()
    ).hexdigest()


def vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def index_case(
    case: Case, engine: sa.Engine | None = None, embed: BatchEmbed = default_embed_batch
) -> IndexReport:
    settings = Settings()
    engine = engine or sync_engine(settings.database_url)
    cv = case_version(case)
    chunks = [c for doc in case.documents for c in chunk_document(doc)]
    shas = {(c.document_id, c.ordinal): text_sha(c, settings.embed_model) for c in chunks}
    with engine.connect() as conn:
        stored = {
            (r.document_id, r.ordinal): r.text_sha for r in conn.execute(EXISTING, {"cv": cv})
        }
    rows: list[dict[str, object]] = []
    embedded = 0
    for doc_id, group in groupby(chunks, key=lambda c: c.document_id):
        doc_chunks = list(group)
        if all(stored.get((doc_id, c.ordinal)) == shas[(doc_id, c.ordinal)] for c in doc_chunks):
            continue
        vectors = embed([embed_text(c) for c in doc_chunks])
        embedded += 1
        rows += [
            {
                "cv": cv,
                "document_id": c.document_id,
                "ordinal": c.ordinal,
                "case_id": case.id,
                "title": c.title,
                "source": c.source,
                "unlocked_by": list(c.unlocked_by),
                "text": c.text,
                "embedding": vector_literal(v),
                "text_sha": shas[(c.document_id, c.ordinal)],
            }
            for c, v in zip(doc_chunks, vectors, strict=True)
        ]
    stale = [{"cv": cv, "document_id": d, "ordinal": o} for (d, o) in stored if (d, o) not in shas]
    if rows or stale:
        with engine.begin() as conn:
            conn.execute(sa.text("select pg_advisory_xact_lock(hashtext(:cv))"), {"cv": cv})
            if rows:
                conn.execute(UPSERT, rows)
            if stale:
                conn.execute(DELETE, stale)
    return IndexReport(case.id, cv, len(chunks), embedded)


def main(paths: Sequence[str]) -> None:
    for path in paths:
        started = time.monotonic()
        report = index_case(Case.model_validate_json(Path(path).read_text()))
        note = (
            "(current)" if report.embedded_documents == 0 else f"{time.monotonic() - started:.1f}s"
        )
        print(f"{report.case_id}  {report.chunks} chunks  {note}")


if __name__ == "__main__":
    main(sys.argv[1:])
