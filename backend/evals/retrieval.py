import json
import math
import sys
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import yaml

from agents.game_master import GameState
from app.config import Settings
from app.db import sync_engine
from engine.evidence import visible_documents
from engine.schema import Case, Id
from evidence import AuthorizedRetriever, PlayerScope, index_case
from evidence.search import default_embed
from security.context import AuthContext, case_version

ROOT = Path(__file__).resolve().parents[2]
QUERIES = Path(__file__).with_name("retrieval_queries.yaml")
REPORTS = ROOT / "reports"
TOP = 10
MIN_WITHHELD_PER_CASE = 2
REPEATS = 3

Expect = Literal["found", "withheld"]


@dataclass(frozen=True)
class LabelledQuery:
    case_id: Id
    query: str
    relevant: Id
    discovered: tuple[Id, ...]
    opened: tuple[Id, ...]


@dataclass(frozen=True)
class Outcome:
    query: LabelledQuery
    expect: Expect
    ranked: tuple[Id, ...]
    leaks: int
    ms: tuple[float, ...]
    embed_ms: tuple[float, ...]


@dataclass(frozen=True)
class Metrics:
    queries: int
    withheld: int
    recall_at_10: float
    mrr: float
    withheld_ok: float
    p95_ms: float
    p95_ms_excl_embed: float
    acl_leaks: int


def load_queries(path: Path, cases: Mapping[Id, Case]) -> list[tuple[LabelledQuery, Expect]]:
    loaded: list[tuple[LabelledQuery, Expect]] = []
    for i, raw in enumerate(yaml.safe_load(path.read_text())):
        where = f"{path.name}[{i}]"
        case = cases.get(raw["case"])
        if case is None:
            raise ValueError(f"{where}: unknown case '{raw['case']}'")
        state = raw.get("state") or {}
        q = LabelledQuery(
            case.id,
            raw["query"],
            raw["relevant"],
            tuple(state.get("discovered", ())),
            tuple(state.get("opened", ())),
        )
        documents = {d.id for d in case.documents}
        clues = {c.id for c in case.clues}
        for kind, ids, known in (
            ("relevant document", [q.relevant], documents),
            ("discovered clue", q.discovered, clues),
            ("opened document", q.opened, documents),
        ):
            unknown = [x for x in ids if x not in known]
            if unknown:
                raise ValueError(f"{where}: unknown {kind} '{unknown[0]}' in case '{case.id}'")
        visible = {d.id for d in visible_documents(case, q.discovered, q.opened)}
        loaded.append((q, "found" if q.relevant in visible else "withheld"))
    for case_id in cases:
        n = sum(1 for q, e in loaded if q.case_id == case_id and e == "withheld")
        if n < MIN_WITHHELD_PER_CASE:
            raise ValueError(
                f"case '{case_id}' has {n} withheld queries, need {MIN_WITHHELD_PER_CASE}"
            )
    return loaded


def p95(samples: Sequence[float]) -> float:
    ordered = sorted(samples)
    return ordered[math.ceil(0.95 * len(ordered)) - 1] if ordered else 0.0


def rank_of(o: Outcome) -> int | None:
    top = o.ranked[:TOP]
    return top.index(o.query.relevant) + 1 if o.query.relevant in top else None


def summarize(outcomes: Sequence[Outcome]) -> Metrics:
    found = [rank_of(o) for o in outcomes if o.expect == "found"]
    withheld = [o for o in outcomes if o.expect == "withheld"]
    total = [ms for o in outcomes for ms in o.ms]
    searching = [t - e for o in outcomes for t, e in zip(o.ms, o.embed_ms, strict=True)]
    return Metrics(
        queries=len(outcomes),
        withheld=len(withheld),
        recall_at_10=sum(r is not None for r in found) / len(found) if found else 0.0,
        mrr=sum(1 / r for r in found if r) / len(found) if found else 0.0,
        withheld_ok=(
            sum(o.query.relevant not in o.ranked for o in withheld) / len(withheld)
            if withheld
            else 1.0
        ),
        p95_ms=p95(total),
        p95_ms_excl_embed=p95(searching),
        acl_leaks=sum(o.leaks for o in outcomes),
    )


def run_query(
    retriever: AuthorizedRetriever,
    timing: list[float],
    case: Case,
    q: LabelledQuery,
    expect: Expect,
    game: str,
) -> Outcome:
    state = GameState(case_id=case.id, game_id=game, discovered=q.discovered, opened=q.opened)
    subject = AuthContext(game, "player", game, case_version(case), 0)
    scope = PlayerScope.of(subject, case, state)
    ms: list[float] = []
    hits = []
    timing.clear()
    for _ in range(REPEATS):
        started = time.perf_counter()
        hits = retriever.search(scope, q.query)
        ms.append((time.perf_counter() - started) * 1000)
    visible = {d.id for d in visible_documents(case, q.discovered, q.opened)}
    return Outcome(
        q,
        expect,
        tuple(h.document_id for h in hits),
        sum(h.document_id not in visible for h in hits),
        tuple(ms),
        tuple(timing),
    )


def render(results: Mapping[str, Metrics]) -> str:
    lines = [
        "# Retrieval eval",
        "",
        f"p95 is nearest-rank over {REPEATS} timed runs of every query. "
        "Recall@10 and MRR cover found queries; withheld is the share of locked-document "
        "queries that returned nothing from that document.",
        "",
        "| case | queries | Recall@10 | MRR | withheld | p95 ms | p95 ms excl. embed | ACL leaks |",
        "|---|---|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {name} | {m.queries} | {m.recall_at_10:.3f} | {m.mrr:.3f} | {m.withheld_ok:.3f} "
        f"| {m.p95_ms:.1f} | {m.p95_ms_excl_embed:.1f} | {m.acl_leaks} |"
        for name, m in results.items()
    ]
    return "\n".join(lines) + "\n"


def run(queries: Path, cases_dir: Path, out_dir: Path) -> dict[str, Metrics]:
    cases = {
        c.id: c for c in (Case.model_validate_json(p.read_text()) for p in cases_dir.glob("*.json"))
    }
    labelled = load_queries(queries, cases)
    engine = sync_engine(Settings().database_url)
    for case in cases.values():
        index_case(case, engine)
    timing: list[float] = []

    def timed_embed(text: str) -> list[float]:
        started = time.perf_counter()
        vector = default_embed(text)
        timing.append((time.perf_counter() - started) * 1000)
        return vector

    retriever = AuthorizedRetriever(engine, timed_embed)
    outcomes: dict[str, list[Outcome]] = defaultdict(list)
    for i, (q, expect) in enumerate(labelled):
        outcomes[q.case_id].append(
            run_query(retriever, timing, cases[q.case_id], q, expect, f"eval-{i}")
        )
    results = {name: summarize(os) for name, os in sorted(outcomes.items())}
    results["overall"] = summarize([o for os in outcomes.values() for o in os])
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "retrieval.json").write_text(
        json.dumps({k: asdict(v) for k, v in results.items()}, indent=2) + "\n"
    )
    (out_dir / "retrieval.md").write_text(render(results))
    return results


def main() -> int:
    results = run(QUERIES, ROOT / "cases", REPORTS)
    print((REPORTS / "retrieval.md").read_text(), end="")
    overall = results["overall"]
    return int(overall.acl_leaks > 0 or overall.withheld_ok < 1.0)


if __name__ == "__main__":
    sys.exit(main())
