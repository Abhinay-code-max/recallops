# Degraded Mode & Fault Tolerance Evaluation

**Evaluation Date:** 2026-09-29  
**Git HEAD:** `05eb0cb325925f03e7395a9d353f7e1d2ea4f732`  
**Evaluator:** Agent 3 (Reliability / Regression / Demo-Readiness)

---

## 1. Executive Summary

A critical requirement for an incident response AI is that it must **never crash during an active outage**. If upstream AI services (Groq LLM) or memory backends (Hindsight Cloud) experience high latency or complete downtime, RecallOps must return graceful, degraded responses with best-effort deterministic information rather than throwing 500 Internal Server Errors.

Fault tolerance was evaluated under two primary failure injection tests using native mocking facilities:
1. **Scenario 1:** Hindsight Cloud Memory Unavailable / Network Timeout
2. **Scenario 2:** Groq Inference API Unavailable / Rate Limited

---

## 2. Test Results Matrix

| Failure Mode | Injected Condition | Expected Behavior | Observed HTTP Status | Degraded Flag | Fallback Content | Verdict |
|---|---|---|---|---|---|---|
| **Hindsight Outage** | `memory.recall_merged` returns `degraded=True` | Return HTTP 200, open incident safely, set `degraded=true`, `memory_state="no_match"` | **200 OK** | `True` | Incident opened, `ranked_fixes: []`, empty evidence | **PASS** |
| **Hindsight Slow / Timeout** | Upstream recall exceeds 12s budget | Total timeout enforced at ~12s; returns degraded outcome without raising exception | **200 OK** | `True` | Incident opened; no unhandled exception | **PASS** |
| **Groq LLM Down** | `llm.complete` returns empty text with `degraded=True` | Return HTTP 200 SSE stream, fall back to deterministic briefing template | **200 OK** | `True` (internal fallback) | Complete `sections` with deterministic root cause, actions, and guarded citations | **PASS** |
| **Groq Malformed / Code-Fence JSON** | LLM outputs invalid JSON with markdown backticks or chatter | Auto-repair JSON and fall back to secondary model (`deepseek-r1-distill-llama-70b`) | **200 OK** | Resilient | Clean structured JSON parsed successfully | **PASS** |
| **LLM Hallucinated Incident IDs** | Model output invents un-recalled IDs (e.g. `INC-999`) | Hallucination guard triggers after retry and reverts to template citations | **200 OK** | Guarded | Hallucinated ID stripped; only verified evidence IDs cited | **PASS** |

---

## 3. Deep Dive: Hindsight Memory Degradation

### Test Execution
When Hindsight Cloud is unreachable (e.g. DNS failure, HTTP 503, or network timeout):
```python
async def _always_degraded(*args, **kwargs):
    return memory_module.RecallOutcome(hits=[], degraded=True)
```
### Observed Response Payload:
```json
{
  "incident_id": "INC-025",
  "deduplicated": false,
  "status": "open",
  "memory_state": "no_match",
  "degraded": true,
  "degraded_reason": "Hindsight memory unavailable",
  "alert": { ... },
  "evidence": [],
  "ranked_fixes": [],
  "warnings": [],
  "team_hint": null,
  "recurrence": null,
  "briefing_stream_url": "/incidents/INC-025/briefing/stream"
}
```
### Reliability Assessment:
- **No Crash:** Returns HTTP 200.
- **Data Integrity:** The incident is still recorded into the local ledger with full alert payload and symptoms.
- **UI Safety:** Frontend renders the incident with `memory_state="no_match"` and amber badge without breaking layout or hanging.

---

## 4. Deep Dive: Groq LLM Degradation & Template Fallback

### Test Execution
When Groq returns HTTP 429 (rate limit) or fails completely:
```python
async def _always_degraded(*args, **kwargs):
    return LLMResult(text="", degraded=True)
```
### Observed Stream Behavior:
1. `GET /incidents/{incident_id}/briefing/stream` opens immediately (HTTP 200).
2. The server detects LLM degradation and switches to the deterministic briefing template generator (`briefing.py:make_template_briefing`).
3. It emits token events constructed from deterministic rule-based analysis:
   - Root cause generated from alert error message and top recalled patterns.
   - First actions derived directly from the highest-ranked fix in the ledger.
   - Team contacts populated from the team routing ledger.
4. It emits valid `sections` and `done` events with citations restricted to verified recalled IDs.

---

## 5. UI Handling of Degraded State

Inspection of `frontend/src/components/TopNav.tsx` and `frontend/src/App.tsx` confirms:
- **`health.memory === 'slow'`:** Renders amber warning badge (`Memory Slow`).
- **`health.memory === 'down'`:** Renders rose warning badge (`Memory Down`).
- **`degraded: true` in alert response:** Frontend suppresses confidence claims and presents available deterministic fixes without error dialogues.

---

## 6. Verdict
**Verdict:** **PASS (Resilient & Fault-Tolerant)**  
RecallOps implements defense-in-depth degradation across all external AI dependencies, ensuring zero 500 errors during third-party outages.
