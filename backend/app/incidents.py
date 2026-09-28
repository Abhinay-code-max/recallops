"""Combined seed + live incident directory, and all in-process live state: live
incidents (INC-023+), live feedback (the runtime overlay on ledger.py's seed counts),
the incident-id counter, and same-pattern dedup.

In-memory by design -- this is a single-process demo backend, and POST /reset already
has to reset the recallops-live Hindsight bank; resetting this module's state alongside
it (reset_live_state()) keeps both in sync. Nothing here talks to Hindsight directly;
routes are responsible for the matching Hindsight retain (recallops-live bank) alongside
calling into this module.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from app import ledger, memory

DEDUPE_WINDOW_MINUTES = 5

_live_incidents: dict[str, dict[str, Any]] = {}
_live_feedback: list[dict[str, Any]] = []
_next_number = 23


def reset_live_state() -> None:
    global _next_number
    _live_incidents.clear()
    _live_feedback.clear()
    _next_number = 23


def next_incident_id() -> str:
    global _next_number
    incident_id = f"INC-{_next_number:03d}"
    _next_number += 1
    return incident_id


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def find_recent_duplicate(service: str, error_signature: str | None, submitted_at: str) -> str | None:
    """Same service + error_signature within DEDUPE_WINDOW_MINUTES of the previous
    alert's submitted_at -- always the alert's own timestamp, never wall-clock time, so
    demo alerts dated days apart never dedupe against each other."""
    if not error_signature:
        return None
    new_ts = _parse_ts(submitted_at)
    for incident_id, incident in _live_incidents.items():
        if incident["service"] != service or incident.get("error_signature") != error_signature:
            continue
        prev_ts = _parse_ts(incident["submitted_at"])
        if abs((new_ts - prev_ts).total_seconds()) <= DEDUPE_WINDOW_MINUTES * 60:
            return incident_id
    return None


def record_alert(incident_id: str, alert: dict[str, Any], evidence_incident_ids: list[str]) -> dict[str, Any]:
    incident = {
        "incident_id": incident_id,
        "title": alert["title"],
        "service": alert["service"],
        "severity": alert["severity"],
        "date": alert.get("submitted_at"),
        "submitted_at": alert.get("submitted_at"),
        "resolver": None,
        "minutes_to_resolve": None,
        "outcome": "open",
        "log_snippet": alert.get("log_snippet"),
        "symptoms": alert.get("symptoms"),
        "error_message": alert.get("error_message"),
        "error_signature": alert.get("error_signature"),
        "root_cause": None,
        "fix_attempts": [],
        "postmortem": None,
        "evidence_incident_ids": evidence_incident_ids,
    }
    _live_incidents[incident_id] = incident
    return incident


def record_feedback(incident_id: str, fix_type: str, outcome: str, notes: str | None) -> None:
    incident = _live_incidents.get(incident_id)
    service = incident["service"] if incident else None
    error_signature = incident.get("error_signature") if incident else None

    _live_feedback.append(
        {
            "incident_id": incident_id,
            "service": service,
            "error_signature": error_signature,
            "fix_type": fix_type,
            "outcome": outcome,
            "notes": notes,
        }
    )
    if incident is not None:
        incident["fix_attempts"].append(
            {"fix_type": fix_type, "outcome": outcome, "minutes_to_effect": None, "resolver": None, "notes": notes}
        )


def record_resolution(incident_id: str, resolver: str, minutes_to_resolve: int | None, postmortem: dict[str, Any]) -> None:
    incident = _live_incidents.get(incident_id)
    if incident is None:
        return
    incident["resolver"] = resolver
    incident["minutes_to_resolve"] = minutes_to_resolve
    incident["root_cause"] = postmortem.get("root_cause")
    incident["postmortem"] = postmortem
    incident["outcome"] = "worked"


def get_incident(incident_id: str) -> dict[str, Any] | None:
    seed = memory.get_seed_incident(incident_id)
    if seed is not None:
        return {
            "incident_id": seed["incident_id"],
            "title": seed["title"],
            "service": seed["service"],
            "severity": seed["severity"],
            "date": seed["timestamp"],
            "resolver": seed["resolver"],
            "minutes_to_resolve": seed["total_minutes_to_resolve"],
            "outcome": seed["fix_attempts"][-1]["outcome"] if seed["fix_attempts"] else "open",
            "log_snippet": seed["log_snippet"],
            "symptoms": seed["symptoms"],
            "root_cause": seed["root_cause"],
            "fix_attempts": seed["fix_attempts"],
            "postmortem": seed["postmortem"],
            "error_signature": seed["error_signature"],
        }
    return _live_incidents.get(incident_id)


def list_incidents() -> list[dict[str, Any]]:
    seed_rows = [
        {
            "incident_id": s["incident_id"],
            "title": s["title"],
            "service": s["service"],
            "severity": s["severity"],
            "date": s["timestamp"],
            "resolver": s["resolver"],
            "minutes_to_resolve": s["total_minutes_to_resolve"],
            "outcome": s["fix_attempts"][-1]["outcome"] if s["fix_attempts"] else "open",
        }
        for s in memory.all_seed_incidents()
    ]
    live_rows = [
        {
            "incident_id": i["incident_id"],
            "title": i["title"],
            "service": i["service"],
            "severity": i["severity"],
            "date": i["date"],
            "resolver": i["resolver"],
            "minutes_to_resolve": i["minutes_to_resolve"],
            "outcome": i["outcome"],
        }
        for i in _live_incidents.values()
    ]
    return seed_rows + live_rows


def get_error_signature(incident_id: str) -> str | None:
    seed = memory.get_seed_incident(incident_id)
    if seed is not None:
        return seed["error_signature"]
    live = _live_incidents.get(incident_id)
    return live.get("error_signature") if live else None


def pattern_pool(top_incident_id: str) -> list[dict[str, Any]]:
    """Incidents (seed + live) sharing the top incident's error_signature, sorted by
    timestamp, each shaped {incident_id, timestamp, fix_attempts: [{fix_type, outcome,
    resolver?}]} -- the input scoring.rank_fixes() and compute_team_hint() need. Seed
    incidents keep their full fix_attempts (including resolver); live incidents' fix
    history is synthesized from live feedback (POST /feedback carries no resolver)."""
    signature = get_error_signature(top_incident_id)
    if signature is None:
        return []

    seed_pool = [inc for inc in memory.all_seed_incidents() if inc["error_signature"] == signature]
    live_pool = [
        {
            "incident_id": inc["incident_id"],
            "timestamp": inc["submitted_at"],
            "fix_attempts": [
                {"fix_type": fb["fix_type"], "outcome": fb["outcome"]}
                for fb in _live_feedback
                if fb["incident_id"] == inc["incident_id"]
            ],
        }
        for inc in _live_incidents.values()
        if inc.get("error_signature") == signature
    ]
    pool = [*seed_pool, *live_pool]
    pool.sort(key=lambda inc: inc["timestamp"])
    return pool


def ledger_counts_for(top_incident_id: str, ledger_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    signature = get_error_signature(top_incident_id)
    if signature is None:
        return {}
    return ledger.counts_for_signature(signature, ledger_data, _live_feedback)


def compute_team_hint(pool: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The resolver who most often worked-fixed this pattern's incidents."""
    resolver_counts: Counter[str] = Counter()
    resolver_incidents: dict[str, list[str]] = {}
    for incident in pool:
        for fix in incident.get("fix_attempts", []):
            if fix.get("outcome") == "worked" and fix.get("resolver"):
                resolver_counts[fix["resolver"]] += 1
                resolver_incidents.setdefault(fix["resolver"], []).append(incident["incident_id"])
    if not resolver_counts:
        return None
    person, count = resolver_counts.most_common(1)[0]
    plural = "s" if count != 1 else ""
    return {
        "person": person,
        "reason": f"Resolved {count} incident{plural} matching this pattern with a working fix.",
        "incident_ids": resolver_incidents[person],
    }


def compute_recurrence(pool: list[dict[str, Any]]) -> dict[str, Any] | None:
    """occurrence_number counts the pool PLUS the alert being handled right now (which
    isn't in the pool yet -- it's being scored against pre-existing incidents)."""
    if not pool:
        return None
    occurrence_number = len(pool) + 1

    interval_days_avg: float | None = None
    if len(pool) >= 2:
        timestamps = sorted(_parse_ts(inc["timestamp"]) for inc in pool)
        gaps = [(b - a).total_seconds() / 86400 for a, b in zip(timestamps, timestamps[1:])]
        interval_days_avg = round(sum(gaps) / len(gaps), 1)

    open_permanent_fix_incident_id = next(
        (inc["incident_id"] for inc in pool if inc.get("permanent_fix_open")), None
    )

    if occurrence_number <= 1:
        return None

    message = f"This is occurrence #{occurrence_number} of this pattern"
    if interval_days_avg is not None:
        message += f", recurring roughly every {interval_days_avg:g} days"
    if open_permanent_fix_incident_id:
        message += f". The permanent fix from {open_permanent_fix_incident_id} is still open."
    else:
        message += "."

    return {
        "occurrence_number": occurrence_number,
        "interval_days_avg": interval_days_avg,
        "open_permanent_fix_incident_id": open_permanent_fix_incident_id,
        "message": message,
    }
