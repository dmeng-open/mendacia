import json
import os
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

from engine.cli import generate
from engine.schema import Case
from security.context import case_version
from tests.engine.generator_scenarios import batch


def query(sql: str, **params: Any) -> list[Any]:
    engine = sa.create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        return list(conn.execute(sa.text(sql), params))


@pytest.fixture
def fresh_catalog() -> None:
    engine = sa.create_engine(os.environ["DATABASE_URL"])
    with engine.begin() as conn:
        conn.execute(sa.text("delete from cases where id like 'manor_batch_%'"))


def test_a_replayed_batch_publishes_only_the_case_that_passes_every_gate(
    fresh_catalog: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("engine.cli.THEMES", tuple(c.theme for c in batch()))
    monkeypatch.setattr("evals.generation_report.REPORTS", tmp_path / "reports")

    assert generate(3, tmp_path / "generated") == 0

    out = capsys.readouterr().out
    assert out.splitlines()[-1] == "first-pass 1/3, final 1/3, security-rejected 1"
    assert "case 2: discarded (max_rounds) after 5 rounds" in out
    assert "case 3: manor_batch_three security-rejected (clara_where)" in out

    [written] = (tmp_path / "generated").glob("*.json")
    case = Case.model_validate_json(written.read_text())
    assert case.id == "manor_batch_one"
    [row] = query("select id, case_version from cases where id like 'manor_batch_%'")
    assert (row.id, row.case_version) == ("manor_batch_one", case_version(case))
    chunks = query(
        "select count(distinct document_id) as docs from evidence_chunks where case_version = :cv",
        cv=case_version(case),
    )
    assert chunks[0].docs == len(case.documents)

    report = json.loads((tmp_path / "reports" / "generation.json").read_text())
    assert (report["attempts"], report["first_pass"], report["final"]) == (3, 1, 1)
    assert (report["security_rejected"], report["discarded"]) == (1, 1)
    assert [r["gate"] for r in report["rows"]] == ["passed", None, "security_rejected"]
    assert "first-pass 1/3, final 1/3, security-rejected 1" in (
        (tmp_path / "reports" / "generation.md").read_text()
    )


def test_a_taken_case_id_gets_a_suffix(fresh_catalog: None) -> None:
    from app.catalog import Catalog, load_cases, publish
    from app.db import sync_engine
    from engine.cli import unique
    from tests.engine.generator_scenarios import manor

    engine = sync_engine(os.environ["DATABASE_URL"])
    catalog = Catalog(load_cases(), engine)
    with engine.begin() as conn:
        publish(conn, manor("manor_batch_one"))

    assert unique(manor("manor"), catalog).id == "manor_2"
    assert unique(manor("manor_batch_one"), catalog).id == "manor_batch_one_2"
    assert unique(manor("manor_batch_new"), catalog).id == "manor_batch_new"
