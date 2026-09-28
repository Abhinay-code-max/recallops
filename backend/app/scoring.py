"""Fix ranking formula (docs/SPEC.md section 5):

    score = similarity * (worked + 0.5*partial + 1) / (attempts + 2) - 0.3 * recent_failures

Pure function, no Hindsight/network/file I/O -- everything it needs is passed in, which
also makes it directly testable against real seed data. Counts come from the ledger
only, never Hindsight (see ledger.py): worked/partial/failed/attempts are read from
ledger_counts (backend/app/ledger.py's counts_for_signature(), already merged with live
feedback by the caller). recent_failures needs per-incident, chronological data that the
pre-aggregated ledger can't give, so it's computed here from `pattern_pool` instead --
the incidents (seed via memory.pattern_siblings(), live incidents of the same pattern,
both assembled by app/incidents.py) sharing the top recalled incident's error_signature.

similarity normalisation -- calibrated from real data, not guessed: recall's raw
scores.final for the 5 demo alerts against the seeded incidents bank ranged 0.42-1.07;
for 3 unrelated nonsense alerts (printer jam, marketing email bounce, parking permit
renewal) it ranged 0.0001-0.0013 -- three orders of magnitude lower. That gap is wide
enough that similarity = clip(raw_relevance, 0, 1) needs no further scaling: real
matches already separate from noise by >300x, and clipping only handles the rare case
where scores.final exceeds 1.0 (it blends multiple signals and isn't bounded like a
probability). See routes/alert.py for the matching no_match threshold, calibrated from
the same numbers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.memory import RecallHit

RECENT_FAILURES_WINDOW = 2


def _similarity(counts_row: dict[str, Any], recalled_by_id: dict[str, RecallHit]) -> float:
    best = 0.0
    for incident_id in counts_row.get("incident_ids", []):
        hit = recalled_by_id.get(incident_id)
        if hit is not None and hit.relevance is not None:
            best = max(best, hit.relevance)
    return min(max(best, 0.0), 1.0)


def _recent_failures(fix_type: str, last_window: list[dict[str, Any]]) -> int:
    count = 0
    for incident in last_window:
        for fix in incident.get("fix_attempts", []):
            if fix["fix_type"] == fix_type and fix["outcome"] == "failed":
                count += 1
    return count


def _last_used_incident_id(fix_type: str, sorted_pool: list[dict[str, Any]]) -> str | None:
    last_id: str | None = None
    last_ts: str | None = None
    for incident in sorted_pool:
        for fix in incident.get("fix_attempts", []):
            if fix["fix_type"] != fix_type:
                continue
            ts = incident["timestamp"]
            if last_ts is None or ts > last_ts:
                last_id, last_ts = incident["incident_id"], ts
    return last_id


@dataclass
class RankedFix:
    rank: int
    fix_type: str
    label: str
    score: float
    similarity: float
    worked: int
    partial: int
    failed: int
    attempts: int
    recent_failures: int
    last_used_incident_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "fix_type": self.fix_type,
            "label": self.label,
            "score": self.score,
            "similarity": self.similarity,
            "worked": self.worked,
            "partial": self.partial,
            "failed": self.failed,
            "attempts": self.attempts,
            "recent_failures": self.recent_failures,
            "last_used_incident_id": self.last_used_incident_id,
        }


def _label(fix_type: str) -> str:
    return fix_type.replace("_", " ").capitalize()


def rank_fixes(
    recalled_hits: list[RecallHit],
    pattern_pool: list[dict[str, Any]],
    ledger_counts: dict[str, dict[str, Any]],
) -> list[RankedFix]:
    """
    recalled_hits: recall_merged()'s deduped hits (only these carry a relevance score).
    pattern_pool: incidents sharing the top recalled incident's error_signature -- seed
        siblings (memory.pattern_siblings) plus any live incidents of the same pattern,
        each a dict with at least incident_id, timestamp (ISO, sortable as a string),
        fix_attempts: [{fix_type, outcome}, ...]. Include the top incident itself.
    ledger_counts: fix_type -> {worked, partial, failed, incident_ids} for this pattern,
        from ledger.counts_for_signature() (already merged with live feedback).

    Returns RankedFix objects sorted by score descending, rank 1..N -- every input to
    the formula is on the object so the UI can show the numbers (API_CONTRACT.md
    RankedFix).
    """
    if not recalled_hits or not ledger_counts:
        return []

    recalled_by_id = {hit.incident_id: hit for hit in recalled_hits}
    sorted_pool = sorted(pattern_pool, key=lambda inc: inc["timestamp"])
    last_window = sorted_pool[-RECENT_FAILURES_WINDOW:]

    ranked: list[RankedFix] = []
    for fix_type, counts in ledger_counts.items():
        worked, partial, failed = counts["worked"], counts["partial"], counts["failed"]
        attempts = worked + partial + failed
        similarity = _similarity(counts, recalled_by_id)
        recent_failures = _recent_failures(fix_type, last_window)
        score = similarity * (worked + 0.5 * partial + 1) / (attempts + 2) - 0.3 * recent_failures

        ranked.append(
            RankedFix(
                rank=0,  # filled in after sorting
                fix_type=fix_type,
                label=_label(fix_type),
                score=round(score, 4),
                similarity=round(similarity, 4),
                worked=worked,
                partial=partial,
                failed=failed,
                attempts=attempts,
                recent_failures=recent_failures,
                last_used_incident_id=_last_used_incident_id(fix_type, sorted_pool),
            )
        )

    ranked.sort(key=lambda r: -r.score)
    for i, r in enumerate(ranked, start=1):
        r.rank = i
    return ranked
