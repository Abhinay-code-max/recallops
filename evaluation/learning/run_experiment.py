"""One-shot RecallOps feedback-learning evaluation.

This script deliberately performs exactly one POST /feedback. It uses the existing
DEMO-1 and DEMO-2 alerts, then resolves DEMO-2 only after the before/after comparison
has been captured so postmortem retention cannot confound the learning delta.
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
OUT = ROOT / "evaluation" / "learning"
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app import incidents, memory  # noqa: E402
from app.main import app  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(name: str, value: Any) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def checked(response):
    response.raise_for_status()
    return response.json()


def snapshot(stage: str, request: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    ranked = response.get("ranked_fixes", [])
    return {
        "stage": stage,
        "captured_at_utc": utc_now(),
        "request": request,
        "incident_id": response["incident_id"],
        "deduplicated": response["deduplicated"],
        "memory_state": response["memory_state"],
        "degraded": response.get("degraded", False),
        "degraded_reason": response.get("degraded_reason"),
        "recalled_evidence_ids": [item["incident_id"] for item in response.get("evidence", [])],
        "evidence": response.get("evidence", []),
        "ranked_fixes": ranked,
        "warnings": response.get("warnings", []),
        "top_recommendation": ranked[0] if ranked else None,
        "recurrence": response.get("recurrence"),
        "raw_response": response,
    }


def warning_kinds(snapshot_data: dict[str, Any]) -> set[str]:
    return {warning["kind"] for warning in snapshot_data.get("warnings", [])}


def make_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_by_fix = {row["fix_type"]: row for row in before["ranked_fixes"]}
    after_by_fix = {row["fix_type"]: row for row in after["ranked_fixes"]}
    rows = []
    for fix_type in sorted(before_by_fix.keys() | after_by_fix.keys()):
        old = before_by_fix.get(fix_type)
        new = after_by_fix.get(fix_type)
        rows.append(
            {
                "fix_type": fix_type,
                "score_before": old["score"] if old else None,
                "score_after": new["score"] if new else None,
                "absolute_score_delta": round(new["score"] - old["score"], 4) if old and new else None,
                "rank_before": old["rank"] if old else None,
                "rank_after": new["rank"] if new else None,
                "rank_delta": new["rank"] - old["rank"] if old and new else None,
                "worked_delta": new["worked"] - old["worked"] if old and new else None,
                "partial_delta": new["partial"] - old["partial"] if old and new else None,
                "failed_delta": new["failed"] - old["failed"] if old and new else None,
                "warning_before": any(fix_type.replace("_", " ") in w["message"].lower() for w in before["warnings"]),
                "warning_after": any(fix_type.replace("_", " ") in w["message"].lower() for w in after["warnings"]),
            }
        )
    before_order = [row["fix_type"] for row in before["ranked_fixes"]]
    after_order = [row["fix_type"] for row in after["ranked_fixes"]]
    before_ids = before["recalled_evidence_ids"]
    after_ids = after["recalled_evidence_ids"]
    return {
        "fix_deltas": rows,
        "recommendation_order_before": before_order,
        "recommendation_order_after": after_order,
        "recommendation_order_changed": before_order != after_order,
        "top_recommendation_changed": (before_order[:1] != after_order[:1]),
        "warning_kinds_before": sorted(warning_kinds(before)),
        "warning_kinds_after": sorted(warning_kinds(after)),
        "warning_behavior_changed": before["warnings"] != after["warnings"],
        "evidence_ids_before": before_ids,
        "evidence_ids_after": after_ids,
        "evidence_changed": before_ids != after_ids,
        "evidence_added": [item for item in after_ids if item not in before_ids],
        "evidence_removed": [item for item in before_ids if item not in after_ids],
        "recurrence_before": before["recurrence"],
        "recurrence_after": after["recurrence"],
    }


async def recall_after_resolution(query: str) -> dict[str, Any]:
    memory.get_client.cache_clear()
    try:
        outcome = await memory.recall_merged([memory.BANK_INCIDENTS, memory.BANK_LIVE], query)
        return {
            "checked_at_utc": utc_now(),
            "query": query,
            "degraded": outcome.degraded,
            "hits": [
                {
                    "incident_id": hit.incident_id,
                    "date": hit.date,
                    "relevance": hit.relevance,
                    "metadata": hit.metadata,
                    "text": hit.text,
                }
                for hit in outcome.hits
            ],
        }
    finally:
        await memory.get_client().aclose()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()

    with TestClient(app) as client:
        reset = checked(client.post("/reset"))
        demos = {item["alert_id"]: item["alert"] for item in checked(client.get("/demo-alerts"))}

        before_request = demos["DEMO-1"]
        before_response = checked(client.post("/alert", json=before_request))
        before = snapshot("before", before_request, before_response)
        write_json("before.json", before)

        feedback_request = {
            "incident_id": before["incident_id"],
            "fix_type": "kill_idle_db_connections",
            "outcome": "worked",
            "notes": "Engineer observed that terminating idle leaked sessions restored checkout capacity for this recurrence.",
        }
        sent_at = utc_now()
        feedback_response = checked(client.post("/feedback", json=feedback_request))
        received_at = utc_now()
        feedback = {
            "event_number": 1,
            "request_sent_at_utc": sent_at,
            "response_received_at_utc": received_at,
            "timestamp_note": "The route timestamps Hindsight retention internally; the API does not return that value. These exact client timestamps bound the server-side event.",
            "request": feedback_request,
            "response": feedback_response,
        }
        write_json("feedback.json", feedback)

        # Allow the single retained feedback memory to become searchable before the
        # next incident. This does not submit any additional feedback or incident.
        time.sleep(3)

        after_request = demos["DEMO-2"]
        after_response = checked(client.post("/alert", json=after_request))
        after = snapshot("after", after_request, after_response)
        write_json("after.json", after)

        delta = make_delta(before, after)
        feedback_by_fix = {row["fix_type"]: row for row in feedback_response["ranked_fixes"]}
        before_by_fix = {row["fix_type"]: row for row in before["ranked_fixes"]}
        observed_fix = feedback_request["fix_type"]
        delta["immediate_feedback_response"] = {
            "explanation": "Same-incident response immediately after the one feedback event; unlike the next-incident comparison, the recall query is unchanged.",
            "fix_type": observed_fix,
            "score_before": before_by_fix[observed_fix]["score"],
            "score_after_feedback": feedback_by_fix[observed_fix]["score"],
            "absolute_score_delta": round(
                feedback_by_fix[observed_fix]["score"] - before_by_fix[observed_fix]["score"], 4
            ),
            "rank_before": before_by_fix[observed_fix]["rank"],
            "rank_after_feedback": feedback_by_fix[observed_fix]["rank"],
            "worked_before": before_by_fix[observed_fix]["worked"],
            "worked_after_feedback": feedback_by_fix[observed_fix]["worked"],
        }
        write_json("delta.json", delta)

        resolve_request = {
            "incident_id": after["incident_id"],
            "resolver": "RecallOps learning evaluation",
            "resolution_notes": "Recurring pool-exhaustion incident closed after the feedback-learning comparison; retain this occurrence as future operational memory.",
            "minutes_to_resolve": 8,
        }
        resolve_response = checked(client.post("/resolve", json=resolve_request))
        resolution = {
            "request": resolve_request,
            "response": resolve_response,
            "resolved_at_utc": utc_now(),
        }
        write_json("resolution.json", resolution)
        future_query = incidents.alert_query(demos["DEMO-5"])

    time.sleep(3)
    retention = asyncio.run(recall_after_resolution(future_query))
    retention["target_incident_id"] = after["incident_id"]
    retention["target_found"] = any(hit["incident_id"] == after["incident_id"] for hit in retention["hits"])
    write_json("retention.json", retention)

    manifest = {
        "head": head,
        "executed_at_utc": utc_now(),
        "reset_response": reset,
        "pattern": "payments-api / postgres_pool_exhaustion",
        "baseline_incident_id": before["incident_id"],
        "next_incident_id": after["incident_id"],
        "feedback_events_submitted": 1,
        "top_recommendation_changed": delta["top_recommendation_changed"],
        "retention_target_found": retention["target_found"],
    }
    write_json("run_manifest.json", manifest)


if __name__ == "__main__":
    main()
