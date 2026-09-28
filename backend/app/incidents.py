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


def alert_query(alert: dict[str, Any]) -> str:
    """The recall query built from an alert -- shared by routes/alert.py,
    routes/feedback.py and scripts/check_recall.py so the calibration script tests
    exactly what production does, never a lookalike. Defensive .get()s: seed incidents
    (also passed through here, e.g. by routes/feedback.py) don't carry error_message."""
    return f"{alert.get('title', '')}. {alert.get('symptoms') or ''} {alert.get('error_message') or ''}"

_live_incidents: dict[str, dict[str, Any]] = {}
_live_feedback: list[dict[str, Any]] = []
_next_number = 23
_memories_stored_live = 0


def reset_live_state() -> None:
    global _next_number, _memories_stored_live
    _live_incidents.clear()
    _live_feedback.clear()
    _next_number = 23
    _memories_stored_live = 0


def record_memories_stored(count: int = 1) -> None:
    """Counter for GET /metrics' counts.memories_stored -- incremented by every
    successful live retain (alert/feedback/postmortem). memories_stored is never
    derived from Hindsight itself (no list-all-memories call); this is the exact count
    of retain calls this process has made since the last reset."""
    global _memories_stored_live
    _memories_stored_live += count


def memories_stored_count() -> int:
    return _memories_stored_live


def next_incident_id() -> str:
    global _next_number
    incident_id = f"INC-{_next_number:03d}"
    _next_number += 1
    return incident_id


def feedback_for(incident_id: str) -> list[dict[str, Any]]:
    return [fb for fb in _live_feedback if fb["incident_id"] == incident_id]


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


def record_alert(
    incident_id: str,
    alert: dict[str, Any],
    evidence_incident_ids: list[str],
    memory_state: str = "no_match",
    ranked_fixes: list[dict[str, Any]] | None = None,
    warnings: list[dict[str, Any]] | None = None,
    team_hint: dict[str, Any] | None = None,
    recurrence: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
        "memory_state": memory_state,
        # Stored at alert time for briefing.generate_sections() grounding:
        "ranked_fixes": ranked_fixes or [],
        "warnings": warnings or [],
        "team_hint": team_hint,
        "recurrence": recurrence,
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


def live_incidents() -> list[dict[str, Any]]:
    return list(_live_incidents.values())


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


def first_resolvable(incident_ids: list[str]) -> str | None:
    """First incident_id (in order) that resolves to a known pattern, seed or live.

    Guards against a real, observed gap: Hindsight's delete_bank isn't guaranteed
    instantly consistent (docs/HINDSIGHT_NOTES.md point 6), so a recall right after
    POST /reset can surface a stale recallops-live memory from a *previous* process/
    session that still outranks the real seed incidents by relevance -- but that
    incident_id no longer exists in this process's freshly-reset local state. Using it
    as the "top" incident for pattern_pool()/scoring would silently produce empty
    ranked_fixes. Skipping to the next hit that actually resolves is more robust than
    trying to make deletion instantaneous.
    """
    for incident_id in incident_ids:
        if get_error_signature(incident_id) is not None:
            return incident_id
    return None


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


def _pattern_stats(pool: list[dict[str, Any]]) -> dict[str, Any]:
    """interval_days_avg + open_permanent_fix_incident_id -- the math shared by
    compute_recurrence() (for /alert, +1 for the new alert being scored) and
    historical_recurrence() (for /insights, no +1 -- just what's happened so far)."""
    interval_days_avg: float | None = None
    if len(pool) >= 2:
        timestamps = sorted(_parse_ts(inc["timestamp"]) for inc in pool)
        gaps = [(b - a).total_seconds() / 86400 for a, b in zip(timestamps, timestamps[1:])]
        interval_days_avg = round(sum(gaps) / len(gaps), 1)
    open_permanent_fix_incident_id = next(
        (inc["incident_id"] for inc in pool if inc.get("permanent_fix_open")), None
    )
    return {"interval_days_avg": interval_days_avg, "open_permanent_fix_incident_id": open_permanent_fix_incident_id}


def _recurrence_from_pool(pool: list[dict[str, Any]], extra_occurrence: int) -> dict[str, Any] | None:
    if not pool:
        return None
    occurrence_number = len(pool) + extra_occurrence
    if occurrence_number <= 1:
        return None

    stats = _pattern_stats(pool)
    message = f"This is occurrence #{occurrence_number} of this pattern" if extra_occurrence else f"Recurred {occurrence_number} times"
    if stats["interval_days_avg"] is not None:
        message += f", recurring roughly every {stats['interval_days_avg']:g} days"
    if stats["open_permanent_fix_incident_id"]:
        message += f". The permanent fix from {stats['open_permanent_fix_incident_id']} is still open."
    else:
        message += "."

    return {"occurrence_number": occurrence_number, **stats, "message": message}


def compute_recurrence(pool: list[dict[str, Any]]) -> dict[str, Any] | None:
    """For POST /alert: occurrence_number counts the pool PLUS the alert being handled
    right now (which isn't in the pool yet -- it's being scored against pre-existing
    incidents)."""
    return _recurrence_from_pool(pool, extra_occurrence=1)


def historical_recurrence(pool: list[dict[str, Any]]) -> dict[str, Any] | None:
    """For GET /insights: occurrence_number is just what's happened so far -- there's no
    new alert being scored."""
    return _recurrence_from_pool(pool, extra_occurrence=0)


def incident_ids_with_outcome(pool: list[dict[str, Any]], fix_type: str, outcome: str) -> list[str]:
    return [
        inc["incident_id"]
        for inc in pool
        if any(fa["fix_type"] == fix_type and fa["outcome"] == outcome for fa in inc.get("fix_attempts", []))
    ]


def build_warnings(ranked_fixes: list, pool: list[dict[str, Any]], recurrence: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Shared by routes/alert.py and routes/feedback.py. Returns plain dicts shaped like
    the Warning contract type -- the caller wraps them in models.Warning."""
    warnings: list[dict[str, Any]] = []
    for fix in ranked_fixes:
        if fix.failed > 0:
            warnings.append(
                {
                    "kind": "failed_fix",
                    "message": f"{fix.label} failed {fix.failed} of {fix.attempts} time(s) for this pattern -- try another fix first.",
                    "incident_ids": incident_ids_with_outcome(pool, fix.fix_type, "failed"),
                }
            )
    if recurrence is not None:
        warnings.append(
            {
                "kind": "recurrence",
                "message": recurrence["message"],
                "incident_ids": [inc["incident_id"] for inc in pool],
            }
        )
        open_id = recurrence.get("open_permanent_fix_incident_id")
        if open_id:
            warnings.append(
                {
                    "kind": "open_permanent_fix",
                    "message": f"The permanent fix for this pattern (raised in {open_id}'s postmortem) is still open.",
                    "incident_ids": [open_id],
                }
            )
    return warnings


def all_incidents_normalized() -> list[dict[str, Any]]:
    """Every incident (seed + live) for GET /insights, normalized to a common shape:
    incident_id, timestamp, service, error_signature, title, permanent_fix_open,
    fix_attempts. Live incidents with no error_signature (can't happen via POST /alert,
    but defensive) are skipped -- they can't be grouped into any pattern."""
    result = list(memory.all_seed_incidents())
    for inc in _live_incidents.values():
        if not inc.get("error_signature"):
            continue
        result.append(
            {
                "incident_id": inc["incident_id"],
                "timestamp": inc["submitted_at"],
                "service": inc["service"],
                "error_signature": inc["error_signature"],
                "title": inc["title"],
                "permanent_fix_open": False,
                "fix_attempts": inc.get("fix_attempts", []),
                "postmortem": inc.get("postmortem"),
            }
        )
    return result


def compute_patterns() -> list[dict[str, Any]]:
    by_signature: dict[str, list[dict[str, Any]]] = {}
    for inc in all_incidents_normalized():
        by_signature.setdefault(inc["error_signature"], []).append(inc)

    patterns = []
    for signature, incs in sorted(by_signature.items()):
        stats = _pattern_stats(incs)
        tags = incs[0].get("pattern_tags") or []
        title_source = tags[0] if tags else signature
        patterns.append(
            {
                "title": title_source.replace("-", " ").replace("_", " ").capitalize(),
                "service": incs[0]["service"],
                "frequency": len(incs),
                "interval_days": stats["interval_days_avg"],
                "incident_ids": sorted(i["incident_id"] for i in incs),
            }
        )
    return patterns


def compute_open_permanent_fixes() -> list[dict[str, Any]]:
    results = []
    for inc in all_incidents_normalized():
        if not inc.get("permanent_fix_open"):
            continue
        postmortem = inc.get("postmortem")
        message = postmortem if isinstance(postmortem, str) else f"The permanent fix for {inc['incident_id']} is still open."
        results.append({"incident_id": inc["incident_id"], "title": inc.get("title", ""), "message": message})
    return results


def compute_team_knowledge() -> list[dict[str, Any]]:
    pattern_counts: dict[str, dict[str, int]] = {}
    resolver_incidents: dict[str, set[str]] = {}

    for inc in all_incidents_normalized():
        signature = inc["error_signature"]
        for fix in inc.get("fix_attempts", []):
            if fix.get("outcome") != "worked" or not fix.get("resolver"):
                continue
            person = fix["resolver"]
            pattern_counts.setdefault(person, {})
            pattern_counts[person][signature] = pattern_counts[person].get(signature, 0) + 1
            resolver_incidents.setdefault(person, set()).add(inc["incident_id"])

    results = []
    for person in sorted(pattern_counts):
        ranked = sorted(pattern_counts[person].items(), key=lambda kv: -kv[1])
        parts = [f"{sig.replace('_', ' ')} {count} time{'s' if count != 1 else ''}" for sig, count in ranked]
        results.append(
            {
                "person": person,
                "summary": f"Resolved {', '.join(parts)}.",
                "incident_ids": sorted(resolver_incidents[person]),
            }
        )
    return results


def compute_fix_speed_comparison() -> dict[str, Any]:
    """first-fix rollback vs resize, average minutes to effect, across every incident
    where that fix_type was the FIRST one attempted (not any attempt -- speed of the
    team's first instinct, which is the comparison that matters for the demo)."""
    rollback_minutes: list[float] = []
    resize_minutes: list[float] = []

    for inc in all_incidents_normalized():
        fix_attempts = inc.get("fix_attempts") or []
        if not fix_attempts:
            continue
        first = fix_attempts[0]
        minutes = first.get("minutes_to_effect")
        if minutes is None:
            continue
        if first["fix_type"] == "rollback_to_previous_deploy":
            rollback_minutes.append(minutes)
        elif first["fix_type"] == "increase_postgres_pool_size":
            resize_minutes.append(minutes)

    rollback_avg = round(sum(rollback_minutes) / len(rollback_minutes), 1) if rollback_minutes else None
    resize_avg = round(sum(resize_minutes) / len(resize_minutes), 1) if resize_minutes else None
    return {
        "first_fix_rollback_avg_min": rollback_avg,
        "first_fix_resize_avg_min": resize_avg,
        "sample_size": len(rollback_minutes) + len(resize_minutes),
        "note": (
            f"Based on {len(rollback_minutes)} incident(s) where rollback was tried first "
            f"and {len(resize_minutes)} where a pool resize was tried first."
        ),
    }
