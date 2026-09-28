/**
 * RecallOps Types
 * Strictly aligned with backend/app/models.py and docs/API_CONTRACT.md
 */

export interface HealthResponse {
  status: 'ok';
  memory: 'ok' | 'slow' | 'down';
  seeding: boolean;
}

export interface SeedResponse {
  seeded: number;
  duration_s: number;
}

export interface ResetResponse {
  ok: boolean;
}

export interface AlertMetrics {
  p99_latency_ms?: number | null;
  error_rate_pct?: number | null;
}

export type Severity = 'SEV1' | 'SEV2' | 'SEV3';

export const parseSeverity = (s?: string | null): Severity => {
  if (s === 'SEV1' || s === 'SEV2' || s === 'SEV3') return s;
  return 'SEV1';
};

export interface Alert {
  alert_id?: string | null;
  service: string;
  severity: Severity;
  title: string;
  symptoms?: string | null;
  error_message: string;
  log_snippet: string;
  error_signature?: string | null;
  submitted_at?: string | null;
  deploy?: string | null;
  metrics?: AlertMetrics | null;
}

export interface Evidence {
  incident_id: string;
  date: string | null;
  relative: string;
  service: string | null;
  severity: string | null;
  excerpt: string;
  relevance: number; // 0..1
  source_bank: string;
}

export interface RankedFix {
  rank: number;
  fix_type: string;
  label: string;
  score: number;
  similarity: number;
  worked: number;
  partial: number;
  failed: number;
  attempts: number;
  recent_failures: number;
  last_used_incident_id?: string | null;
}

export interface Warning {
  kind: 'failed_fix' | 'recurrence' | 'open_permanent_fix';
  message: string;
  incident_ids: string[];
}

export interface TeamHint {
  person: string;
  reason: string;
  incident_ids: string[];
}

export interface Recurrence {
  occurrence_number: number;
  interval_days_avg: number | null;
  open_permanent_fix_incident_id: string | null;
  message: string;
}

export interface BriefingSources {
  root_cause: string[];
  first_actions: string[];
  last_fixed_by: string | null;
}

export interface BriefingSections {
  root_cause: string;
  blast_radius: string;
  first_actions: string[]; // exactly 3 items
  last_fixed_by: string | null;
  sources: BriefingSources;
}

export interface PostmortemTimelineEntry {
  time: string;
  event: string;
}

export interface Postmortem {
  timeline: PostmortemTimelineEntry[];
  root_cause: string;
  fix: string;
  action_items: string[];
}

export interface AlertResponse {
  incident_id: string;
  deduplicated: boolean;
  status: 'open';
  memory_state: 'empty' | 'no_match' | 'matched';
  alert: Alert;
  evidence: Evidence[];
  ranked_fixes: RankedFix[];
  warnings: Warning[];
  team_hint: TeamHint | null;
  recurrence: Recurrence | null;
  briefing_stream_url: string;
  degraded?: boolean;
  degraded_reason?: string | null;
}

export interface FeedbackRequest {
  incident_id: string;
  fix_type: string;
  outcome: 'worked' | 'partial' | 'failed';
  notes?: string | null;
}

export interface FeedbackResponse {
  ranked_fixes: RankedFix[];
  warnings: Warning[];
  memories_stored: number;
}

export interface ResolveRequest {
  incident_id: string;
  resolver: string;
  resolution_notes?: string | null;
  minutes_to_resolve?: number | null;
}

export interface ResolveResponse {
  postmortem: Postmortem;
  memories_stored: number;
}

export interface DemoAlertOut {
  alert_id: string;
  target_capability: string;
  title: string;
  alert: Alert;
}

export interface IncidentSummary {
  incident_id: string;
  title: string;
  service: string;
  severity: string;
  date: string | null;
  resolver: string | null;
  minutes_to_resolve: number | null;
  outcome: 'worked' | 'partial' | 'failed' | 'open';
}

export interface FixAttempt {
  fix_type: string;
  outcome: string;
  minutes_to_effect?: number | null;
  resolver?: string | null;
  notes?: string | null;
}

export interface IncidentDetail extends IncidentSummary {
  log_snippet?: string | null;
  symptoms?: string | null;
  root_cause?: string | null;
  fix_attempts: FixAttempt[];
  postmortem?: Postmortem | string | null;
}

export interface CompareRequest {
  alert: Alert;
}

export interface WithoutMemory {
  text: string;
}

export interface WithMemory {
  sections: BriefingSections;
  evidence: Evidence[];
  ranked_fixes: RankedFix[];
  warnings: Warning[];
}

export interface CompareResponse {
  without_memory: WithoutMemory;
  with_memory: WithMemory;
}

export interface MetricsCounts {
  incidents_handled: number;
  memories_stored: number;
}

export interface RealSeriesPoint {
  n: number;
  incident_id: string;
  mttr_min: number;
  live?: boolean;
}

export interface SimulatedSeriesPoint {
  n: number;
  mttr_min: number;
  accuracy: number;
}

export interface MetricsResponse {
  counts: MetricsCounts;
  historical_avg_mttr_min: number;
  real_series: RealSeriesPoint[];
  simulated_series: SimulatedSeriesPoint[];
  simulated: true;
}

export interface InsightPattern {
  title: string;
  service: string;
  frequency: number;
  interval_days: number | null;
  incident_ids: string[];
}

export interface RecurringInsight {
  service: string;
  title: string;
  recurrence: Recurrence;
}

export interface OpenPermanentFix {
  incident_id: string;
  title: string;
  message: string;
}

export interface TeamKnowledge {
  person: string;
  summary: string;
  incident_ids: string[];
}

export interface FixSpeedComparison {
  first_fix_rollback_avg_min: number | null;
  first_fix_resize_avg_min: number | null;
  sample_size: number;
  note: string;
}

export interface InsightsResponse {
  patterns: InsightPattern[];
  recurring: RecurringInsight[];
  open_permanent_fixes: OpenPermanentFix[];
  team_knowledge: TeamKnowledge[];
  fix_speed_comparison: FixSpeedComparison;
  reflect_summary: string | null;
  reflect_status: 'ready' | 'pending' | 'failed';
}

export interface ChatRequest {
  incident_id?: string | null;
  question: string;
}

export interface ChatResponse {
  answer: string;
  evidence: Evidence[];
}

// UI helper types
export interface TeamMember {
  id: string;
  name: string;
  email: string;
  role: string;
  team_service: string;
  on_call_status: 'Primary On-Call' | 'Secondary On-Call' | 'Available' | 'Off-Duty';
  initials: string;
  avatar_color?: string;
  is_lead?: boolean;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  evidence?: Evidence[];
}

export interface ActivityItem {
  id: string;
  timestamp: string;
  category: 'incident' | 'memory' | 'feedback' | 'resolution' | 'postmortem' | 'assignment' | 'approval' | 'mitigation';
  title: string;
  detail: string;
  actor: string;
  actor_role?: string;
  is_agent?: boolean;
  incident_id?: string;
  service?: string;
  severity?: string;
  badge_label?: string;
}
