"""GET /metrics -- real_series is exact seed MTTR (backend/data/seed_incidents.json's
total_minutes_to_resolve) plus resolved live incidents appended with live=true;
simulated_series comes from backend/data/seed_metrics.json's simulated_with_recallops
(already flagged simulated:true there -- see backend/app/seeding.py);
historical_avg_mttr_min is computed from the seeded incidents only, never live ones (a
handful of live incidents would skew a small-sample average); counts.memories_stored is
the exact seeded item count (computed, not hardcoded to "60" -- 22 incidents + N fix
attempts + 7 team profiles, whatever the seed data currently has) plus
incidents.memories_stored_count() (every live retain since the last reset).
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

from app import incidents
from app.models import MetricsCounts, MetricsResponse, RealSeriesPoint, SimulatedSeriesPoint

router = APIRouter()
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def _load_seed_incidents() -> list[dict]:
    return json.loads((DATA_DIR / "seed_incidents.json").read_text(encoding="utf-8"))


def _load_seed_team() -> list[dict]:
    return json.loads((DATA_DIR / "seed_team.json").read_text(encoding="utf-8"))


def _load_seed_metrics() -> list[dict]:
    return json.loads((DATA_DIR / "seed_metrics.json").read_text(encoding="utf-8"))


def _seeded_item_count(seed_incidents: list[dict]) -> int:
    return len(seed_incidents) + sum(len(i["fix_attempts"]) for i in seed_incidents) + len(_load_seed_team())


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics() -> MetricsResponse:
    seed_incidents = _load_seed_incidents()
    seed_metrics = _load_seed_metrics()

    real_series = [
        RealSeriesPoint(n=idx + 1, incident_id=inc["incident_id"], mttr_min=inc["total_minutes_to_resolve"])
        for idx, inc in enumerate(seed_incidents)
    ]

    resolved_live = sorted(
        (inc for inc in incidents.live_incidents() if inc.get("minutes_to_resolve") is not None),
        key=lambda inc: inc["incident_id"],
    )
    for offset, inc in enumerate(resolved_live):
        real_series.append(
            RealSeriesPoint(
                n=len(seed_incidents) + offset + 1,
                incident_id=inc["incident_id"],
                mttr_min=inc["minutes_to_resolve"],
                live=True,
            )
        )

    simulated_series = [
        SimulatedSeriesPoint(
            n=row["sequence"],
            mttr_min=row["simulated_with_recallops"]["mttr_minutes"],
            accuracy=row["simulated_with_recallops"]["suggestion_accuracy"],
        )
        for row in seed_metrics
    ]

    historical_avg_mttr_min = round(sum(inc["total_minutes_to_resolve"] for inc in seed_incidents) / len(seed_incidents), 2)

    counts = MetricsCounts(
        incidents_handled=len(seed_incidents) + len(incidents.live_incidents()),
        memories_stored=_seeded_item_count(seed_incidents) + incidents.memories_stored_count(),
    )

    return MetricsResponse(
        counts=counts,
        historical_avg_mttr_min=historical_avg_mttr_min,
        real_series=real_series,
        simulated_series=simulated_series,
        simulated=True,
    )
