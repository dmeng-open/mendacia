import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

from app.config import Settings
from app.db import sync_engine
from evals.report import build, markdown

GAMES = [
    ("g1", "manor", {"accusation": {"correct": True}, "questions_left": 16}),
    ("g2", "manor", {"accusation": {"correct": False}, "questions_left": 10}),
    ("g3", "gallery", {"accusation": None, "questions_left": 20}),
]
TURNS = [
    ("g1", {"drafts": 1, "turn_ms": 1000, "fell_back": False}, {"code": None}),
    ("g1", {"drafts": 1, "turn_ms": 3000, "fell_back": False}, {"code": None}),
    ("g2", {"drafts": 1, "turn_ms": 2000, "fell_back": True}, {"code": None}),
    ("g3", {"turn_ms": 500}, {"code": "screened"}),
    ("c1", {"drafts": 1, "turn_ms": 4000, "fell_back": False}, {"code": None}),
]
FINDINGS = [
    ("a1", "attack", "tool_misuse", "broker", "held", "", "c1"),
    ("a2", "attack", "spoiler_extraction", "extractor", "leaked", "step 1: culprit_secret:x", None),
    ("a3", "attack", "cross_session", "api", "leaked", "step 1: allowed a request", None),
    ("a4", "attack", "direct_injection", "suspect", "error", "budget_exceeded", None),
    ("n1", "normal", "normal", "suspect", "passed", "", None),
    ("n2", "normal", "normal", "suspect", "rejected", "step 1: refused (screened)", None),
]


def seed(conn: sa.Connection, run: str, sim: str, ids: dict[str, str]) -> None:
    def q(sql: str, **p: Any) -> None:
        conn.execute(sa.text(sql), p)

    q(
        "insert into security_eval_runs (id, status, games, max_usd, cost_usd, sim_run_id,"
        " policy_version) values (:r, 'finished', 3, 5, 1.5, :s, 'p')",
        r=run,
        s=sim,
    )
    for key, case, state in [*GAMES, ("c1", "manor", {"accusation": None, "questions_left": 19})]:
        q(
            "insert into games (id, case_id, case_version, session_digest, state)"
            " values (:g, :c, 'v', 'd', cast(:s as jsonb))",
            g=ids[key],
            c=case,
            s=json.dumps(state),
        )
    for key, _, _ in GAMES:
        for model, tokens, cost in (("m-strong", 300, 0.3), ("m-fast", 60, 0.03)):
            q(
                "insert into llm_calls (model, role, purpose, game_id, prompt_tokens,"
                " completion_tokens, cost_usd, latency_ms, mode, run_id)"
                " values (:m, 'strong', 'detective', :g, :t, 0, :c, 1, 'live', :s)",
                m=model,
                g=ids[key],
                t=tokens,
                c=cost,
                s=sim,
            )
    for n, (key, verdict, outcome) in enumerate(TURNS):
        q(
            "insert into turns (game_id, idempotency_key, args_hash, state_version, tool,"
            " reply, verdict, outcome) values (:g, :k, 'h', :n, 'ask_question', 'ok',"
            " cast(:v as jsonb), cast(:o as jsonb))",
            g=ids[key],
            k=f"k{n}",
            n=n,
            v=json.dumps(verdict),
            o=json.dumps(outcome),
        )
    for key in ("g1", "g1", "c1"):
        q(
            "insert into verifier_events (game_id, suspect, turn, rule, claim, action)"
            " values (:g, 'hobbs', 1, 'block_culprit', 'c', 'rewrite')",
            g=ids[key],
        )
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for key, offset, rows in (("g1", 0, (1, 2, 7)), ("g2", 1, (5, 5, 10))):
        for action, ms in zip(("retrieve", "verify", "ask_question"), rows, strict=True):
            q(
                "insert into security_events (created_at, trace_id, game_id, actor_type, action,"
                " resource_type, policy_version, decision, reason_code, latency_ms, case_version,"
                " state_version, decision_trace) values (:t, 't', :g, 'player', :a, 'tool', 'p',"
                " 'allow', 'released', :ms, 'v', 0, '[]')",
                t=start + timedelta(seconds=offset),
                g=ids[key],
                a=action,
                ms=ms,
            )
    for entry, kind, cls, comp, outcome, detail, ref in FINDINGS:
        q(
            "insert into security_findings (run_id, entry, kind, case_id, case_version,"
            " policy_version, attack_class, component, outcome, severity, replay_ref, detail)"
            " values (:r, :e, :k, 'manor', 'v', 'p', :c, :comp, :o, 'none', :ref, :d)",
            r=run,
            e=entry,
            k=kind,
            c=cls,
            comp=comp,
            o=outcome,
            ref=ids[ref] if ref else None,
            d=detail,
        )


def test_each_metric_equals_its_hand_computed_value(tmp_path: Path) -> None:
    run, sim = uuid.uuid4().hex, uuid.uuid4().hex
    ids = {k: uuid.uuid4().hex for k in ("g1", "g2", "g3", "c1")}
    with sync_engine(Settings().database_url).begin() as conn:
        seed(conn, run, sim, ids)
    retrieval = tmp_path / "retrieval.json"
    retrieval.write_text(json.dumps({"overall": {"recall_at_10": 0.9, "mrr": 0.8, "acl_leaks": 0}}))
    inventory = tmp_path / "inventory.json"
    rows = [{"agent": "suspect", "tools": [], "layers": ["knowledge"], "planned": None}]
    inventory.write_text(json.dumps({"agents": rows}))

    r = build(run, retrieval=retrieval, inventory=inventory)

    assert r.games == 3
    assert r.quality == {
        "solve_rate": 0.5,
        "avg_questions_solved": 4,
        "block_rate_per_100_turns": 60.0,
        "fallback_rate": 0.2,
        "recall_at_10": 0.9,
        "mrr": 0.8,
        "turn_p95_ms": pytest.approx(3800.0),
    }
    assert r.security == {
        "unauthorized_tool_success": 1,
        "spoiler_success": 1,
        "canary_leaks": 0,
        "acl_leaks": 0,
        "false_reject_rate": 0.5,
        "first_game_block_rate": pytest.approx(2 / 3),
        "guard_p50_ms": pytest.approx(15.0),
        "guard_p99_ms": pytest.approx(19.9),
        "attacks": 4,
        "attacks_held": 1,
        "errors": 1,
    }
    assert r.cost_by_model == {
        "m-strong": {"tokens_per_game": 300.0, "usd_per_game": pytest.approx(0.3)},
        "m-fast": {"tokens_per_game": 60.0, "usd_per_game": pytest.approx(0.03)},
    }
    assert r.heatmap["broker"]["tool_misuse"] == 1.0
    assert r.heatmap["extractor"]["spoiler_extraction"] == 0.0
    assert r.heatmap["api"]["cross_session"] == 0.0
    assert r.heatmap["suspect"]["direct_injection"] is None
    assert r.inventory == [
        {"agent": "suspect", "tools": [], "layers": ["knowledge"], "status": "OK"}
    ]
    text = markdown(r)
    assert "Spoiler success 1, Canary leaks 0, Unauthorized tool success 1." in text
    assert "| broker | - | - | - | - | 1.00 |" in text
