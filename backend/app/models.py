"""Pydantic request/response models. Shapes come from docs/API_CONTRACT.md -- single
agent now, so the contract can be edited in the same commit as the code that needs it
when a shape turns out to be wrong, rather than only ever adding to it.
"""
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"]
    memory: Literal["ok", "slow", "down"]


class SeedResponse(BaseModel):
    seeded: int
    duration_s: float


class ResetResponse(BaseModel):
    ok: bool


# --- shared contract types --------------------------------------------------------------
class AlertMetrics(BaseModel):
    p99_latency_ms: float | None = None
    error_rate_pct: float | None = None


class Alert(BaseModel):
    alert_id: str | None = None
    service: str
    severity: Literal["SEV1", "SEV2", "SEV3"]
    title: str
    symptoms: str | None = None
    error_message: str
    log_snippet: str
    error_signature: str | None = None
    submitted_at: str | None = None
    deploy: str | None = None
    metrics: AlertMetrics | None = None


class Evidence(BaseModel):
    incident_id: str
    date: str | None
    relative: str
    service: str | None
    severity: str | None
    excerpt: str
    relevance: float
    source_bank: str


class RankedFixOut(BaseModel):
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


class Warning(BaseModel):
    kind: Literal["failed_fix", "recurrence", "open_permanent_fix"]
    message: str
    incident_ids: list[str]


class TeamHint(BaseModel):
    person: str
    reason: str
    incident_ids: list[str]


class Recurrence(BaseModel):
    occurrence_number: int
    interval_days_avg: float | None
    open_permanent_fix_incident_id: str | None
    message: str


class BriefingSections(BaseModel):
    root_cause: str
    blast_radius: str
    first_actions: list[str] = Field(min_length=3, max_length=3)
    last_fixed_by: str | None = None


class PostmortemTimelineEntry(BaseModel):
    time: str
    event: str


class Postmortem(BaseModel):
    timeline: list[PostmortemTimelineEntry]
    root_cause: str
    fix: str
    action_items: list[str]


# --- POST /alert --------------------------------------------------------------------
class AlertResponse(BaseModel):
    incident_id: str
    deduplicated: bool
    status: Literal["open"]
    memory_state: Literal["empty", "no_match", "matched"]
    alert: Alert
    evidence: list[Evidence]
    ranked_fixes: list[RankedFixOut]
    warnings: list[Warning]
    team_hint: TeamHint | None
    recurrence: Recurrence | None
    briefing_stream_url: str
    degraded: bool = False
    degraded_reason: str | None = None


# --- POST /feedback -------------------------------------------------------------------
class FeedbackRequest(BaseModel):
    incident_id: str
    fix_type: str
    outcome: Literal["worked", "partial", "failed"]
    notes: str | None = None


class FeedbackResponse(BaseModel):
    ranked_fixes: list[RankedFixOut]
    warnings: list[Warning]
    memories_stored: int


# --- POST /resolve -------------------------------------------------------------------
class ResolveRequest(BaseModel):
    incident_id: str
    resolver: str
    resolution_notes: str | None = None
    minutes_to_resolve: int | None = None


class ResolveResponse(BaseModel):
    postmortem: Postmortem
    memories_stored: int


# --- GET /demo-alerts, /incidents ----------------------------------------------------
class DemoAlertOut(BaseModel):
    alert_id: str
    target_capability: str
    title: str
    alert: Alert


class IncidentSummary(BaseModel):
    incident_id: str
    title: str
    service: str
    severity: str
    date: str | None
    resolver: str | None
    minutes_to_resolve: int | float | None
    outcome: Literal["worked", "partial", "failed", "open"]


class FixAttemptOut(BaseModel):
    fix_type: str
    outcome: str
    minutes_to_effect: int | float | None = None
    resolver: str | None = None
    notes: str | None = None


class IncidentDetail(IncidentSummary):
    log_snippet: str | None = None
    symptoms: str | None = None
    root_cause: str | None = None
    fix_attempts: list[FixAttemptOut] = []
    postmortem: Postmortem | str | None = None


# --- POST /compare -------------------------------------------------------------------
class CompareRequest(BaseModel):
    alert: Alert


class WithoutMemory(BaseModel):
    text: str


class WithMemory(BaseModel):
    sections: BriefingSections
    evidence: list[Evidence]
    ranked_fixes: list[RankedFixOut]
    warnings: list[Warning]


class CompareResponse(BaseModel):
    without_memory: WithoutMemory
    with_memory: WithMemory


# --- GET /metrics -------------------------------------------------------------------
class MetricsCounts(BaseModel):
    incidents_handled: int
    memories_stored: int


class RealSeriesPoint(BaseModel):
    n: int
    incident_id: str
    mttr_min: float
    live: bool = False


class SimulatedSeriesPoint(BaseModel):
    n: int
    mttr_min: float
    accuracy: float


class MetricsResponse(BaseModel):
    counts: MetricsCounts
    historical_avg_mttr_min: float
    real_series: list[RealSeriesPoint]
    simulated_series: list[SimulatedSeriesPoint]
    simulated: Literal[True] = True


# --- GET /insights -------------------------------------------------------------------
class InsightPattern(BaseModel):
    title: str
    service: str
    frequency: int
    interval_days: float | None
    incident_ids: list[str]


class RecurringInsight(BaseModel):
    service: str
    title: str
    recurrence: Recurrence


class OpenPermanentFix(BaseModel):
    incident_id: str
    title: str
    message: str


class TeamKnowledge(BaseModel):
    person: str
    summary: str
    incident_ids: list[str]


class FixSpeedComparison(BaseModel):
    first_fix_rollback_avg_min: float | None
    first_fix_resize_avg_min: float | None
    sample_size: int
    note: str


class InsightsResponse(BaseModel):
    patterns: list[InsightPattern]
    recurring: list[RecurringInsight]
    open_permanent_fixes: list[OpenPermanentFix]
    team_knowledge: list[TeamKnowledge]
    fix_speed_comparison: FixSpeedComparison
    reflect_summary: str


# --- POST /chat -------------------------------------------------------------------
class ChatRequest(BaseModel):
    incident_id: str | None = None
    question: str


class ChatResponse(BaseModel):
    answer: str
    evidence: list[Evidence]
