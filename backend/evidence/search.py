import time
import uuid
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

import sqlalchemy as sa

from agents.game_master import GameState
from app import llm
from engine.evidence import visible_documents
from engine.schema import Case, Id
from evidence.index import vector_literal
from security.context import AuthContext, case_version
from security.events import AuditRow, TraceStep, audit_row, log_decisions
from security.policy import Decision, PolicyContext, Resource, authorize

RRF_K = 60
CANDIDATES = 20
MAX_QUERY_CHARS = 500
ACTION = "search_evidence"

Embed = Callable[[str], list[float]]

HYBRID_SQL = sa.text("""
with scope as (
    select * from evidence_chunks
    where case_version = :cv and document_id = any(CAST(:visible AS text[]))
),
q as (
    select to_tsquery('english', replace(plainto_tsquery('english', :q)::text, '&', '|')) as tsq
),
vec as (
    select 'vector' as retriever,
           row_number() over (order by dist, document_id, ordinal) as rank,
           document_id, ordinal, title, source, unlocked_by, text
    from (
        select *, embedding <=> CAST(:qvec AS vector) as dist from scope
        order by dist, document_id, ordinal limit :n
    ) nearest
),
txt as (
    select 'text' as retriever,
           row_number() over (order by score desc, document_id, ordinal) as rank,
           document_id, ordinal, title, source, unlocked_by, text
    from (
        select scope.*, ts_rank_cd(tsv, q.tsq) as score from scope, q where tsv @@ q.tsq
        order by score desc, document_id, ordinal limit :n
    ) matched
)
select r.retriever, r.rank, r.document_id, r.title, r.source, r.unlocked_by,
       ts_headline('english', r.text, q.tsq,
                   'StartSel=[[, StopSel=]], MaxWords=35, MinWords=15, MaxFragments=2') as headline
from (select * from vec union all select * from txt) r, q
""")


class NotAPlayer(ValueError):
    pass


class CaseMismatch(ValueError):
    pass


@dataclass(frozen=True)
class PlayerScope:
    subject: AuthContext
    case: Case
    state: GameState

    @classmethod
    def of(cls, subject: AuthContext, case: Case, state: GameState) -> "PlayerScope":
        if subject.actor_type != "player":
            raise NotAPlayer(subject.actor_type)
        if case_version(case) != subject.case_version or state.case_id != case.id:
            raise CaseMismatch(case.id)
        return cls(subject, case, state)

    @property
    def visible(self) -> frozenset[Id]:
        docs = visible_documents(self.case, self.state.discovered, self.state.opened)
        return frozenset(d.id for d in docs)

    @property
    def policy(self) -> PolicyContext:
        unlocks = frozenset({*self.state.discovered, *self.state.opened})
        return PolicyContext(self.subject.state_version, unlocks=unlocks, purpose=ACTION)


@dataclass(frozen=True)
class Hit:
    document_id: Id
    title: str
    source: Id
    visibility: Literal["open", "unlocked"]
    highlight: str
    score: float
    vector_rank: int | None
    text_rank: int | None


@dataclass(frozen=True)
class Ranked:
    retriever: Literal["vector", "text"]
    rank: int
    document_id: Id
    title: str
    source: Id
    unlocked_by: tuple[Id, ...]
    headline: str


def normalize_query(raw: str) -> str:
    printable = "".join(ch for ch in raw if ch != "\x00" and not 0xD800 <= ord(ch) <= 0xDFFF)
    return " ".join(printable.split())[:MAX_QUERY_CHARS].strip()


def fuse(rows: Sequence[Ranked], k: int = RRF_K) -> list[Hit]:
    by_doc: dict[Id, dict[str, Ranked]] = defaultdict(dict)
    for row in sorted(rows, key=lambda r: r.rank):
        by_doc[row.document_id].setdefault(row.retriever, row)
    hits = []
    for doc_id, best in by_doc.items():
        shown = best.get("text") or best["vector"]
        hits.append(
            Hit(
                document_id=doc_id,
                title=shown.title,
                source=shown.source,
                visibility="unlocked" if shown.unlocked_by else "open",
                highlight=shown.headline,
                score=sum(1 / (k + r.rank) for r in best.values()),
                vector_rank=best["vector"].rank if "vector" in best else None,
                text_rank=best["text"].rank if "text" in best else None,
            )
        )
    return sorted(
        hits,
        key=lambda h: (-h.score, min(r for r in (h.vector_rank, h.text_rank) if r), h.document_id),
    )


def default_embed(text: str) -> list[float]:
    return llm.embed([text], purpose="search_query").vectors[0]


def leak_row(scope: PlayerScope, document_id: Id, decision: Decision, ms: float) -> AuditRow:
    return audit_row(
        scope.subject,
        trace_id=uuid.uuid4().hex,
        turn_id=None,
        action=ACTION,
        resource_type="document",
        decision=Decision("deny", f"acl_leak:{decision.reason_code}", decision.policy_version),
        trace=[
            TraceStep(step="policy", outcome=f"sql_pass:{document_id}", ms=0.0),
            TraceStep(step="policy", outcome=f"authorize:{decision.reason_code}", ms=ms),
        ],
    )


class AuthorizedRetriever:
    def __init__(self, engine: sa.Engine, embed: Embed = default_embed) -> None:
        self._engine = engine
        self._embed = embed

    def search(self, ctx: PlayerScope, query: str, k: int = 10) -> list[Hit]:
        q = normalize_query(query)
        if not q:
            return []
        params = {
            "cv": ctx.subject.case_version,
            "visible": sorted(ctx.visible),
            "q": q,
            "qvec": vector_literal(self._embed(q)),
            "n": CANDIDATES,
        }
        with self._engine.connect() as conn:
            rows = [
                Ranked(
                    r.retriever,
                    r.rank,
                    r.document_id,
                    r.title,
                    r.source,
                    tuple(r.unlocked_by),
                    r.headline,
                )
                for r in conn.execute(HYBRID_SQL, params)
            ]
        kept, leaks = self._recheck(ctx, fuse(rows))
        log_decisions(leaks)
        return kept[:k]

    def _recheck(self, ctx: PlayerScope, hits: list[Hit]) -> tuple[list[Hit], list[AuditRow]]:
        docs = {d.id: d for d in ctx.case.documents}
        version = case_version(ctx.case)
        policy = ctx.policy
        kept: list[Hit] = []
        leaks: list[AuditRow] = []
        for hit in hits:
            doc = docs.get(hit.document_id)
            started = time.perf_counter()
            if doc is None:
                decision = Decision("deny", "unknown_doc")
            else:
                resource = Resource(
                    "document",
                    doc.id,
                    version,
                    "player",
                    visibility=doc.visibility,
                )
                decision = authorize(ctx.subject, "open_document", resource, policy)
            if decision.allowed:
                kept.append(hit)
            else:
                ms = (time.perf_counter() - started) * 1000
                leaks.append(leak_row(ctx, hit.document_id, decision, ms))
        return kept, leaks
