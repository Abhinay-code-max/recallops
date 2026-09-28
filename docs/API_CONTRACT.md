# RecallOps API contract (v1, frozen)

Base URL: `VITE_API_BASE` (default `http://localhost:8000`). JSON, snake_case, timestamps ISO-8601 UTC.
"Relative" strings ("3 weeks ago") are computed by the server from the alert's `submitted_at`, never by the client.
Every JSON response may include `degraded: boolean` and `degraded_reason: string|null`. Errors: HTTP 4xx/5xx with `{"error":{"code":"string","message":"string"}}`.
If Hindsight or the LLM is slow/down the server still answers 200 with `degraded: true` and best-effort content.

## Types
```
Alert        { alert_id?, service, severity: "SEV1"|"SEV2"|"SEV3", title, symptoms?, error_message, log_snippet,
               error_signature?, submitted_at?, deploy?, metrics?: { p99_latency_ms?, error_rate_pct? } }
Evidence     { incident_id, date, relative, service, severity, excerpt, relevance /*0..1*/, source_bank }
RankedFix    { rank, fix_type, label, score, similarity, worked, partial, failed, attempts, recent_failures,
               last_used_incident_id|null }
Warning      { kind: "failed_fix"|"recurrence"|"open_permanent_fix", message, incident_ids: string[] }
TeamHint     { person, reason, incident_ids: string[] }
Recurrence   { occurrence_number, interval_days_avg|null, open_permanent_fix_incident_id|null, message }
BriefingSections { root_cause, blast_radius, first_actions: string[3], last_fixed_by|null }
Postmortem   { timeline: {time,event}[], root_cause, fix, action_items: string[] }
```

## Endpoints
| Method + path | Request | Response |
|---|---|---|
| GET /health | - | `{status:"ok", memory:"ok"|"slow"|"down", seeding:boolean}` |
| POST /seed | - | `{seeded:int, duration_s:number}` (idempotent) |
| POST /reset | - | `{ok:true}` (returns memory to freshly seeded state) |
| GET /demo-alerts | - | `[{alert_id, target_capability, title, alert:Alert}]` |
| POST /alert | `Alert` | `{incident_id, deduplicated:boolean, status:"open", memory_state:"empty"|"no_match"|"matched", alert:Alert, evidence:Evidence[], ranked_fixes:RankedFix[], warnings:Warning[], team_hint:TeamHint|null, recurrence:Recurrence|null, briefing_stream_url:string}` |
| GET {briefing_stream_url} (SSE) | - | events: `token` `{text}`; `sections` `BriefingSections`; `done` `{cited_incident_ids:string[]}`; `error` `{message}` |
| POST /feedback | `{incident_id, fix_type, outcome:"worked"|"partial"|"failed", notes?}` | `{ranked_fixes:RankedFix[], warnings:Warning[], memories_stored:int}` |
| POST /resolve | `{incident_id, resolver, resolution_notes?, minutes_to_resolve?}` | `{postmortem:Postmortem, memories_stored:int}` |
| POST /chat | `{incident_id?, question}` | `{answer:string, evidence:Evidence[]}` |
| POST /compare | `{alert:Alert}` | `{without_memory:{text}, with_memory:{sections:BriefingSections, evidence:Evidence[], ranked_fixes:RankedFix[], warnings:Warning[]}}` |
| GET /incidents | - | `[{incident_id, title, service, severity, date, resolver, minutes_to_resolve, outcome:"worked"|"partial"|"failed"|"open"}]` |
| GET /incidents/{id} | - | list fields plus `{log_snippet, symptoms, root_cause, fix_attempts:[{fix_type,outcome,minutes_to_effect,resolver,notes}], postmortem:string|Postmortem}` |
| GET /insights | - | `{patterns:[{title, service, frequency:int, interval_days|null, incident_ids}], recurring:[{service, title, recurrence:Recurrence}], open_permanent_fixes:[{incident_id,title,message}], team_knowledge:[{person,summary,incident_ids}], fix_speed_comparison:{first_fix_rollback_avg_min, first_fix_resize_avg_min, sample_size, note}, reflect_summary:string|null, reflect_status:"ready"|"pending"|"failed"}` |
| GET /metrics | - | `{counts:{incidents_handled,memories_stored}, historical_avg_mttr_min, real_series:[{n,incident_id,mttr_min,live?:boolean}], simulated_series:[{n,mttr_min,accuracy}], simulated:true}` |

Notes
- The simulated series must be labelled "Simulated" in the UI. The real series is the seeded history.
- `score` and its inputs (similarity, worked, partial, failed, recent_failures) are always shown in the UI so the ranking is transparent.
- `memory_state` drives the UI banners: `empty` = no history yet, `no_match` = history exists but nothing similar.
- `reflect_summary` on GET /insights is narrative only, from one `reflect` call given the other fields as context -- the UI must never read a number out of it; every number in the response is computed from structured data.
- GET /insights returns immediately with the deterministic fields; `reflect_summary` is `null` and `reflect_status` is `"pending"` while reflect runs in the background (started at app startup, after POST /seed, POST /reset, POST /feedback and POST /resolve). Poll GET /insights again to pick up `"ready"` (or `"failed"`, still with the deterministic fields intact).
- GET /health's `seeding` flag is true while a cold-start auto-seed (an empty Hindsight Cloud bank at startup) is running in the background; POST /seed's own response is unaffected either way.

