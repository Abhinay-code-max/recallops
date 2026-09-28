"""Validate backend/data/{seed_incidents,seed_team,demo_alerts,seed_metrics}.json against the
shape required by docs/SPEC.md section 6 and docs/PROMPTS.md Prompt 1.

Run: backend/.venv/Scripts/python scripts/validate_seed.py
"""
import datetime
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "backend" / "data"

SERVICES = {"payments-api", "order-worker", "auth-service", "search-api", "notification-service"}
SEVERITIES = {"SEV1", "SEV2", "SEV3"}
OUTCOMES = {"worked", "partial", "failed"}
RANGE_START = datetime.date(2026, 5, 10)
RANGE_END = datetime.date(2026, 9, 10)

TEXT_PREFIX_RE = re.compile(
    r"^Date: (?P<date>\S+) \| (?P<incident_id>INC-\d{3}) \| (?P<service>[\w-]+) \| (?P<severity>SEV[1-3])\n"
)

PATTERN_EXPECTED_COUNTS = {
    "pool-exhaustion-friday-deploy": 4,
    "redis-oom-monday": 3,
    "kafka-lag-sale": 2,
    "expired-tls-cert": 1,
    "bad-config-flag": 1,
}

failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


def load(name):
    path = DATA_DIR / name
    check(path.exists(), f"{name} does not exist at {path}")
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    incidents = load("seed_incidents.json")
    team = load("seed_team.json")
    demo_alerts = load("demo_alerts.json")
    metrics = load("seed_metrics.json")

    if incidents is None or team is None or demo_alerts is None or metrics is None:
        print("\n".join(failures), file=sys.stderr)
        return 1

    # --- seed_incidents.json ------------------------------------------------
    check(len(incidents) == 22, f"expected 22 incidents, got {len(incidents)}")

    ids = [inc["incident_id"] for inc in incidents]
    check(len(ids) == len(set(ids)), "incident_id values are not unique")
    check(
        ids == [f"INC-{n:03d}" for n in range(1, len(incidents) + 1)],
        f"incident_id values are not sequential INC-001.. : {ids}",
    )

    doc_ids = [inc["document_id"] for inc in incidents]
    check(len(doc_ids) == len(set(doc_ids)), "document_id values are not unique")
    for inc in incidents:
        check(
            inc["document_id"] == f"incident-{inc['incident_id']}",
            f"{inc['incident_id']}: document_id {inc['document_id']!r} is not stable "
            f"('incident-{inc['incident_id']}')",
        )

    prev_dt = None
    pattern_counts = {k: 0 for k in PATTERN_EXPECTED_COUNTS}
    permanent_fix_open_ids = []
    all_outcomes = set()
    payments_rollback_failures = 0
    all_resolvers = set()

    for inc in incidents:
        inc_id = inc["incident_id"]
        check(inc["service"] in SERVICES, f"{inc_id}: unknown service {inc['service']!r}")
        check(inc["severity"] in SEVERITIES, f"{inc_id}: unknown severity {inc['severity']!r}")

        ts_raw = inc["timestamp"]
        try:
            dt = datetime.datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except ValueError:
            failures.append(f"{inc_id}: unparsable timestamp {ts_raw!r}")
            dt = None
        if dt is not None:
            check(
                RANGE_START <= dt.date() <= RANGE_END,
                f"{inc_id}: timestamp {ts_raw} outside expected range {RANGE_START}..{RANGE_END}",
            )
            if prev_dt is not None:
                check(dt > prev_dt, f"{inc_id}: timestamp {ts_raw} is not strictly after the previous incident's")
            prev_dt = dt

        # text field format
        text = inc["text"]
        m = TEXT_PREFIX_RE.match(text)
        check(m is not None, f"{inc_id}: text field does not start with 'Date: ... | INC-xxx | service | SEVn'")
        if m:
            check(m.group("incident_id") == inc_id, f"{inc_id}: text prefix incident id mismatch ({m.group('incident_id')})")
            check(m.group("service") == inc["service"], f"{inc_id}: text prefix service mismatch")
            check(m.group("severity") == inc["severity"], f"{inc_id}: text prefix severity mismatch")
            check(m.group("date") == ts_raw, f"{inc_id}: text prefix date {m.group('date')} != timestamp {ts_raw}")

        check(f"\nTitle: {inc['title']}\n" in text, f"{inc_id}: text is missing the Title line")
        check(
            f"\nError signature: {inc['error_signature']}\n" in text,
            f"{inc_id}: text is missing the Error signature line",
        )
        check(
            inc["log_snippet"] in text,
            f"{inc_id}: text does not contain the raw (unmasked) log_snippet verbatim",
        )
        check(f"\nPostmortem: {inc['postmortem']}" in text, f"{inc_id}: text is missing the Postmortem line")

        fix_attempts = inc.get("fix_attempts", [])
        check(len(fix_attempts) >= 1, f"{inc_id}: has no fix_attempts")
        for fa in fix_attempts:
            check(fa["outcome"] in OUTCOMES, f"{inc_id}: unknown fix outcome {fa['outcome']!r}")
            all_outcomes.add(fa["outcome"])
            all_resolvers.add(fa["resolver"])
            if inc["service"] == "payments-api" and fa["fix_type"] == "rollback_to_previous_deploy" and fa["outcome"] == "failed":
                payments_rollback_failures += 1

        for tag in inc.get("pattern_tags", []):
            check(tag in PATTERN_EXPECTED_COUNTS, f"{inc_id}: unexpected pattern tag {tag!r}")
            pattern_counts[tag] = pattern_counts.get(tag, 0) + 1

        if inc.get("permanent_fix_open"):
            permanent_fix_open_ids.append(inc_id)

        # weekday checks for planted patterns
        if dt is not None and "pool-exhaustion-friday-deploy" in inc.get("pattern_tags", []):
            check(dt.weekday() == 4, f"{inc_id}: pool-exhaustion-friday-deploy incident is not on a Friday ({ts_raw})")
        if dt is not None and "redis-oom-monday" in inc.get("pattern_tags", []):
            check(dt.weekday() == 0, f"{inc_id}: redis-oom-monday incident is not on a Monday ({ts_raw})")

    for tag, expected in PATTERN_EXPECTED_COUNTS.items():
        check(pattern_counts.get(tag, 0) == expected, f"pattern {tag!r}: expected {expected} incidents, found {pattern_counts.get(tag, 0)}")

    check(OUTCOMES.issubset(all_outcomes), f"fix outcomes are not mixed, only saw: {all_outcomes}")
    check(payments_rollback_failures >= 2, f"expected >=2 failed payments-api rollbacks, found {payments_rollback_failures}")
    check(len(permanent_fix_open_ids) == 1, f"expected exactly 1 incident with permanent_fix_open=true, found {permanent_fix_open_ids}")

    # --- seed_team.json -------------------------------------------------------
    check(len(team) == 7, f"expected 7 engineers, got {len(team)}")
    names = [e["name"] for e in team]
    check(len(names) == len(set(names)), "engineer names are not unique")
    for eng in team:
        check(bool(eng.get("specialties")), f"{eng.get('name')}: missing specialties")
        check(bool(eng.get("preference")), f"{eng.get('name')}: missing preference")

    # --- demo_alerts.json -------------------------------------------------------
    check(len(demo_alerts) == 5, f"expected 5 demo alerts, got {len(demo_alerts)}")
    expected_capabilities = {"recall", "failure_warning", "reflect_pattern", "team_routing", "recurring_detector"}
    found_capabilities = {a["target_capability"] for a in demo_alerts}
    check(
        found_capabilities == expected_capabilities,
        f"demo_alerts target_capability values {found_capabilities} != {expected_capabilities}",
    )

    for alert in demo_alerts:
        expected_ids = alert.get("expected_incident_ids", [])
        check(bool(expected_ids), f"{alert['alert_id']}: no expected_incident_ids")
        for eid in expected_ids:
            check(eid in ids, f"{alert['alert_id']}: expected_incident_ids references unknown incident {eid}")
        check(alert["service"] in SERVICES, f"{alert['alert_id']}: unknown service {alert['service']!r}")
        check(alert["severity"] in SEVERITIES, f"{alert['alert_id']}: unknown severity {alert['severity']!r}")

    # --- seed_metrics.json -------------------------------------------------------
    check(len(metrics) == len(incidents), f"seed_metrics has {len(metrics)} rows, expected {len(incidents)}")
    metric_ids = [m["incident_id"] for m in metrics]
    check(metric_ids == ids, "seed_metrics incident_id order does not match seed_incidents order")

    if len(metrics) >= 5:
        first_avg = sum(m["mttr_minutes"] for m in metrics[:5]) / 5
        last_avg = sum(m["mttr_minutes"] for m in metrics[-5:]) / 5
        check(first_avg > last_avg, f"MTTR does not trend down: first-5 avg {first_avg} <= last-5 avg {last_avg}")
        check(metrics[0]["mttr_minutes"] >= 40, f"first MTTR {metrics[0]['mttr_minutes']} is not close to the ~47 min spec target")
        check(metrics[-1]["mttr_minutes"] <= 15, f"last MTTR {metrics[-1]['mttr_minutes']} is not close to the ~9 min spec target")

        first_acc = sum(m["suggestion_accuracy"] for m in metrics[:5]) / 5
        last_acc = sum(m["suggestion_accuracy"] for m in metrics[-5:]) / 5
        check(last_acc > first_acc, f"suggestion_accuracy does not trend up: first-5 avg {first_acc} >= last-5 avg {last_acc}")

    # --- summary -------------------------------------------------------
    if failures:
        print(f"FAILED: {len(failures)} check(s) failed\n")
        for f in failures:
            print(f" - {f}")
        return 1

    print("OK: seed data passed all checks")
    print(f" - {len(incidents)} incidents, {len(ids)} unique IDs, dates {incidents[0]['timestamp']} .. {incidents[-1]['timestamp']}")
    print(f" - pattern counts: {pattern_counts}")
    print(f" - payments-api failed rollbacks: {payments_rollback_failures}")
    print(f" - permanent_fix_open: {permanent_fix_open_ids}")
    print(f" - {len(team)} engineers: {', '.join(names)}")
    print(f" - {len(demo_alerts)} demo alerts covering: {sorted(found_capabilities)}")
    print(f" - MTTR trend: {metrics[0]['mttr_minutes']} -> {metrics[-1]['mttr_minutes']} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
