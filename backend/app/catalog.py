from collections.abc import Iterator, Mapping
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.schemas import CaseSummary
from engine.schema import Case, Id
from security.context import case_version

CASES_DIR = Path(__file__).resolve().parents[2] / "cases"
METADATA = sa.MetaData()
CASES = sa.Table(
    "cases",
    METADATA,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("case_version", sa.Text),
    sa.Column("title", sa.Text),
    sa.Column("summary", sa.Text),
    sa.Column("body", JSONB),
    sa.Column("generation_id", sa.Text),
    sa.Column("published_at", sa.DateTime(timezone=True)),
)


def load_cases(directory: Path = CASES_DIR) -> dict[Id, Case]:
    found = (Case.model_validate_json(p.read_text()) for p in sorted(directory.glob("*.json")))
    return {c.id: c for c in found}


def publish(conn: sa.Connection, case: Case, generation_id: str | None = None) -> None:
    values = {
        "case_version": case_version(case),
        "title": case.title,
        "summary": case.summary,
        "body": case.model_dump(mode="json"),
        "generation_id": generation_id,
    }
    stmt = insert(CASES).values(id=case.id, **values)
    conn.execute(stmt.on_conflict_do_update(index_elements=["id"], set_=values))


class Catalog(Mapping[Id, Case]):
    """The hand-written cases in `cases/`, then every published case in the database."""

    def __init__(self, files: Mapping[Id, Case], engine: sa.Engine) -> None:
        self._files = dict(files)
        self._published: dict[Id, Case] = {}
        self._engine = engine

    def __getitem__(self, case_id: Id) -> Case:
        if case_id in self._files:
            return self._files[case_id]
        if case_id not in self._published:
            with self._engine.connect() as conn:
                body = conn.scalar(sa.select(CASES.c.body).where(CASES.c.id == case_id))
            if body is None:
                raise KeyError(case_id)
            self._published[case_id] = Case.model_validate(body)
        return self._published[case_id]

    def __iter__(self) -> Iterator[Id]:
        return iter({**self._published, **self._files})

    def __len__(self) -> int:
        return len({**self._published, **self._files})

    async def summaries(self, engine: AsyncEngine) -> list[CaseSummary]:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    sa.select(CASES.c.id, CASES.c.title, CASES.c.summary).order_by(
                        CASES.c.published_at
                    )
                )
            ).all()
        listed = [
            CaseSummary(id=c.id, title=c.title, summary=c.summary) for c in self._files.values()
        ]
        listed += [
            CaseSummary(id=r.id, title=r.title, summary=r.summary)
            for r in rows
            if r.id not in self._files
        ]
        return listed
