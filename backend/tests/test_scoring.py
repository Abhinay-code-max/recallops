import json
from pathlib import Path

from app import ledger
from app.memory import RecallHit
from app.scoring import rank_fixes

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_incidents() -> list[dict]:
    return json.loads((DATA_DIR / "seed_incidents.json").read_text(encoding="utf-8"))


def _pool_and_counts_for(top_incident_id: str, relevances: dict[str, float]):
    incidents = _load_incidents()
    top = next(i for i in incidents if i["incident_id"] == top_incident_id)
    signature = top["error_signature"]
    pool = [i for i in incidents if i["error_signature"] == signature]
    ledger_data = ledger.compute_ledger(incidents)
    counts = ledger.counts_for_signature(signature, ledger_data)
    hits = [RecallHit(incident_id=iid, date=None, relevance=rel, text="") for iid, rel in relevances.items()]
    return hits, pool, counts


# Real relevance scores measured live (see scoring.py's module docstring / the
# calibration run): DEMO-1's recall against the seeded incidents bank.
_POOL_EXHAUSTION_RELEVANCES = {"INC-002": 0.825, "INC-021": 0.729, "INC-009": 0.698, "INC-017": 0.471}


def test_seed_ranking_matches_real_seed_data() -> None:
    hits, pool, counts = _pool_and_counts_for("INC-002", _POOL_EXHAUSTION_RELEVANCES)
    ranked = rank_fixes(hits, pool, counts)

    order = [r.fix_type for r in ranked]
    assert order == [
        "increase_postgres_pool_size",
        "kill_idle_db_connections",
        "restart_payments_pods",
        "rollback_to_previous_deploy",
    ]

    resize = ranked[0]
    assert (resize.worked, resize.partial, resize.failed, resize.attempts) == (3, 0, 0, 3)

    rollback = next(r for r in ranked if r.fix_type == "rollback_to_previous_deploy")
    assert rollback.failed == 2
    assert rollback.score < 0  # both its failures are within the recent-failures window


def test_one_extra_failed_kill_idle_drops_it_below_restart() -> None:
    hits, pool, counts = _pool_and_counts_for("INC-002", _POOL_EXHAUSTION_RELEVANCES)

    # Add one more kill_idle_db_connections failure, attributed to the pattern's most
    # recent incident so it falls inside the recent-failures window.
    counts["kill_idle_db_connections"]["failed"] += 1
    counts["kill_idle_db_connections"]["incident_ids"].append("INC-021")
    pool = sorted(pool, key=lambda i: i["timestamp"])
    pool[-1] = dict(pool[-1])
    pool[-1]["fix_attempts"] = [*pool[-1]["fix_attempts"], {"fix_type": "kill_idle_db_connections", "outcome": "failed"}]

    ranked = rank_fixes(hits, pool, counts)
    by_type = {r.fix_type: r for r in ranked}

    assert by_type["kill_idle_db_connections"].score < by_type["restart_payments_pods"].score
    # order overall should now read: resize, restart, kill_idle, rollback
    assert [r.fix_type for r in ranked][:2] == ["increase_postgres_pool_size", "restart_payments_pods"]


def test_empty_ledger_returns_no_ranked_fixes() -> None:
    hits = [RecallHit(incident_id="INC-999", date=None, relevance=0.9, text="")]
    assert rank_fixes(hits, [], {}) == []


def test_no_recalled_hits_returns_no_ranked_fixes() -> None:
    pool = [{"incident_id": "INC-X", "timestamp": "2026-01-01T00:00:00Z", "fix_attempts": []}]
    counts = {"some_fix": {"worked": 1, "partial": 0, "failed": 0, "incident_ids": ["INC-X"]}}
    assert rank_fixes([], pool, counts) == []


def test_conflicting_outcomes_recommends_more_frequent_recent_success() -> None:
    pool = [
        {
            "incident_id": "INC-A",
            "timestamp": "2026-01-01T00:00:00Z",
            "fix_attempts": [{"fix_type": "fix_x", "outcome": "worked"}],
        },
        {
            "incident_id": "INC-B",
            "timestamp": "2026-02-01T00:00:00Z",
            "fix_attempts": [
                {"fix_type": "fix_x", "outcome": "failed"},
                {"fix_type": "fix_y", "outcome": "worked"},
            ],
        },
        {
            "incident_id": "INC-C",
            "timestamp": "2026-03-01T00:00:00Z",
            "fix_attempts": [{"fix_type": "fix_y", "outcome": "worked"}],
        },
    ]
    ledger_counts = {
        "fix_x": {"worked": 1, "partial": 0, "failed": 1, "incident_ids": ["INC-A", "INC-B"]},
        "fix_y": {"worked": 2, "partial": 0, "failed": 0, "incident_ids": ["INC-B", "INC-C"]},
    }
    hits = [RecallHit(incident_id=iid, date=None, relevance=0.8, text="") for iid in ("INC-A", "INC-B", "INC-C")]

    ranked = rank_fixes(hits, pool, ledger_counts)

    # fix_x's one failure is recent (within the last-2 window); fix_y worked twice with
    # no recent failure -- more frequent AND more recent success should win.
    assert ranked[0].fix_type == "fix_y"
    assert ranked[0].score > next(r for r in ranked if r.fix_type == "fix_x").score
