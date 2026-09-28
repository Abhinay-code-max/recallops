import pytest

from app import incidents


@pytest.fixture(autouse=True)
def _reset_live_state():
    incidents.reset_live_state()
    yield
    incidents.reset_live_state()


def test_next_incident_id_starts_at_023_and_increments() -> None:
    assert incidents.next_incident_id() == "INC-023"
    assert incidents.next_incident_id() == "INC-024"


def test_team_hint_for_kafka_pattern_is_rahul_mehta() -> None:
    pool = incidents.pattern_pool("INC-006")
    hint = incidents.compute_team_hint(pool)
    assert hint is not None
    assert hint["person"] == "Rahul Mehta"
    assert set(hint["incident_ids"]) == {"INC-006", "INC-020"}


def test_recurrence_for_pool_exhaustion_pattern() -> None:
    pool = incidents.pattern_pool("INC-002")
    recurrence = incidents.compute_recurrence(pool)
    assert recurrence is not None
    assert recurrence["occurrence_number"] == 5  # 4 seed incidents + the new alert
    assert recurrence["open_permanent_fix_incident_id"] == "INC-021"
    assert recurrence["interval_days_avg"] is not None


def test_recurrence_second_occurrence_for_single_prior_incident_pattern() -> None:
    # INC-012 is the only prior expired_tls_cert incident -- a new alert matching this
    # pattern is genuinely occurrence #2 (INC-012 itself, plus the new alert).
    pool = incidents.pattern_pool("INC-012")
    recurrence = incidents.compute_recurrence(pool)
    assert recurrence is not None
    assert recurrence["occurrence_number"] == 2
    assert recurrence["interval_days_avg"] is None  # only one prior incident, no gap to average


def test_recurrence_none_when_pattern_has_no_history_at_all() -> None:
    # An unknown incident_id has no error_signature to look up, so no pattern pool.
    assert incidents.pattern_pool("INC-999") == []
    assert incidents.compute_recurrence([]) is None


def test_dedupe_within_window_on_same_service_and_signature() -> None:
    incident_id = incidents.next_incident_id()
    incidents.record_alert(
        incident_id,
        {
            "title": "t",
            "service": "payments-api",
            "severity": "SEV1",
            "submitted_at": "2026-09-11T15:00:00Z",
            "error_signature": "postgres_pool_exhaustion",
        },
        [],
    )
    dup = incidents.find_recent_duplicate("payments-api", "postgres_pool_exhaustion", "2026-09-11T15:04:00Z")
    assert dup == incident_id


def test_no_dedupe_outside_window() -> None:
    incident_id = incidents.next_incident_id()
    incidents.record_alert(
        incident_id,
        {
            "title": "t",
            "service": "payments-api",
            "severity": "SEV1",
            "submitted_at": "2026-09-11T15:00:00Z",
            "error_signature": "postgres_pool_exhaustion",
        },
        [],
    )
    dup = incidents.find_recent_duplicate("payments-api", "postgres_pool_exhaustion", "2026-09-11T15:06:00Z")
    assert dup is None


def test_no_dedupe_across_demo_alerts_days_apart() -> None:
    # Demo alerts are dated days apart on purpose -- never dedupe using wall-clock time.
    incident_id = incidents.next_incident_id()
    incidents.record_alert(
        incident_id,
        {
            "title": "t",
            "service": "payments-api",
            "severity": "SEV1",
            "submitted_at": "2026-09-11T15:02:00Z",
            "error_signature": "postgres_pool_exhaustion",
        },
        [],
    )
    dup = incidents.find_recent_duplicate("payments-api", "postgres_pool_exhaustion", "2026-09-18T14:47:00Z")
    assert dup is None


def test_feedback_and_resolution_roundtrip() -> None:
    incident_id = incidents.next_incident_id()
    incidents.record_alert(
        incident_id,
        {
            "title": "t",
            "service": "payments-api",
            "severity": "SEV1",
            "submitted_at": "2026-09-11T15:02:00Z",
            "error_signature": "postgres_pool_exhaustion",
            "log_snippet": "ERROR ...",
            "symptoms": "checkout failing",
        },
        ["INC-002"],
    )
    incidents.record_feedback(incident_id, "rollback_to_previous_deploy", "failed", "didn't help")
    incident = incidents.get_incident(incident_id)
    assert incident["fix_attempts"] == [
        {"fix_type": "rollback_to_previous_deploy", "outcome": "failed", "minutes_to_effect": None, "resolver": None, "notes": "didn't help"}
    ]
    assert incident["outcome"] == "open"

    incidents.record_resolution(
        incident_id,
        "Priya Nair",
        9,
        {"timeline": [], "root_cause": "leak", "fix": "resize", "action_items": []},
    )
    incident = incidents.get_incident(incident_id)
    assert incident["resolver"] == "Priya Nair"
    assert incident["minutes_to_resolve"] == 9
    assert incident["outcome"] == "worked"
    assert incident["root_cause"] == "leak"


def test_list_incidents_includes_seed_and_live() -> None:
    incident_id = incidents.next_incident_id()
    incidents.record_alert(
        incident_id,
        {"title": "t", "service": "payments-api", "severity": "SEV1", "submitted_at": "2026-09-11T15:02:00Z"},
        [],
    )
    rows = incidents.list_incidents()
    ids = {r["incident_id"] for r in rows}
    assert "INC-002" in ids  # seed
    assert incident_id in ids  # live


def test_reset_clears_live_state() -> None:
    incidents.next_incident_id()
    incidents.record_alert(
        "INC-023",
        {"title": "t", "service": "payments-api", "severity": "SEV1", "submitted_at": "2026-09-11T15:02:00Z"},
        [],
    )
    incidents.reset_live_state()
    assert incidents.get_incident("INC-023") is None
    assert incidents.next_incident_id() == "INC-023"
