# Alert Deduplication Reliability Evaluation

**Evaluation Date:** 2026-09-29  
**Git HEAD:** `05eb0cb325925f03e7395a9d353f7e1d2ea4f732`  
**Evaluator:** Agent 3 (Reliability / Regression / Demo-Readiness)

---

## 1. Executive Summary

During live production outages, monitoring systems (e.g. Datadog, PagerDuty, Alertmanager) routinely emit repeat alert notifications every 30 to 60 seconds for the same firing rule. If an incident response agent creates a new incident record for every incoming webhook, responder attention is fragmented and system state is corrupted.

RecallOps implements a 5-minute sliding window deduplication algorithm keyed on `(service, error_signature)` or `(service, title)`.

---

## 2. Test Execution & Verification

Three sequential alert submission tests were conducted in a clean runtime environment:

### Step 1: Initial Alert Ingestion (DEMO-1)
- **Service:** `payments-service`
- **Error Signature:** `PG-POOL-EXHAUSTED`
- **Submission Time:** `2026-04-18T10:15:00Z`
- **Result:**
  - `incident_id`: `INC-023`
  - `deduplicated`: `false` (initial incident)
  - `status`: `open`

### Step 2: Immediate Duplicate Submission (< 5 Minute Window)
- **Service:** `payments-service`
- **Error Signature:** `PG-POOL-EXHAUSTED`
- **Submission Time:** Within the active deduplication window
- **Result:**
  - `incident_id`: `INC-023` (Identical ID reused)
  - `deduplicated`: `true`
  - `status`: `open`
  - **Ledger Verification:** No duplicate incident row was created; ledger count remained steady.

### Step 3: Distinct Alert Ingestion (DEMO-2 / Different Signature)
- **Service:** `order-worker`
- **Error Signature:** `KAFKA-CONSUMER-TIMEOUT`
- **Result:**
  - `incident_id`: `INC-024` (New unique incident ID assigned)
  - `deduplicated`: `false`
  - `status`: `open`

### Step 4: Outside Window Verification
- As verified in backend regression test `tests/test_alert.py::test_no_dedup_when_demo_alerts_are_days_apart`:
  - When the same alert arrives days apart (or outside the 5-minute dedupe window), deduplication evaluates to `false` and tracks the event as a new recurrence occurrence.

---

## 3. Results Summary

| Test Case | Expected Behavior | Observed Result | Status |
|---|---|---|---|
| **Same Alert Within 5m Window** | Reuse existing `incident_id`, return `deduplicated: true` | Reused `INC-023`, `deduplicated: true` | **PASS** |
| **Different Alert Ingestion** | Assign fresh `incident_id`, return `deduplicated: false` | Assigned `INC-024`, `deduplicated: false` | **PASS** |
| **Ledger Row Integrity** | Prevent uncontrolled duplicate incident proliferation | Total open incidents in ledger = 2 | **PASS** |

---

## 4. Verdict
**Verdict:** **PASS (Production Ready)**  
Alert deduplication successfully suppresses redundant alerts within the 5-minute window while preserving independent tracking for genuine separate outages.
