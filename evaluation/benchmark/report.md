# RecallOps memory-vs-stateless benchmark

**Question.** Does the same reasoning model give more useful incident-response guidance when RecallOps/Hindsight operational memory is available than when it sees only the current alert?

| | |
|---|---|
| HEAD evaluated | `05eb0cb325925f03e7395a9d353f7e1d2ea4f732` (branch `main`; same at collect time) |
| Model | `openai/gpt-oss-120b` (Groq) for **all 30 calls**, both conditions. Fallback `qwen/qwen3.8-27b` was never used. temperature 0.2 |
| Cases | 15 (10 distinct patterns), 1 generation per case per condition, no re-runs, nothing dropped |
| Collected | 2026-09-29 06:29:59Z → 06:33:38Z (UTC). Scoring frozen at 06:29:37Z, before any model call |
| Requests | A: 15 ok / 0 degraded / 0 failed. B: 15 ok / 0 degraded / 0 failed / 0 template fallbacks. 2 Groq `RateLimitError` retries (absorbed by the `llm.py` retry; other agents share the key) |
| Hindsight | ping ok (0.59s). All 15 cases `memory_state=matched`. No `recallops-live` evidence appeared, so the other agents' live-bank writes did not contaminate B |

## Method (frozen before observing outputs)

- **A – Stateless:** one `llm.complete()` call (same wrapper, same JSON schema as the production briefing) with only title/service/severity/symptoms/error. No Hindsight, ledger, history or recurrence data.
- **B – RecallOps:** the production `with_memory` path of `POST /compare`, replicated call-for-call in-process: `analysis.analyze_alert()` (Hindsight recall of `incidents`+`recallops-live`, ledger ranking, warnings, team hint, recurrence) then `generate_sections()` (guarded LLM briefing). No side effects, no retain, no seed/reset, FastAPI lifespan never started. The alert text given to B's recall and to A is identical.
- **Cases:** C01–C05 are the 5 project demo alerts verbatim (`demo_tuned=true`: production calibration used them). C06–C15 are 10 new alerts I wrote as fresh occurrences of other seeded patterns (not copies of seed log lines).
- **Ground truth** is derived from `backend/data/seed_incidents.json` (pattern pools, fix outcomes, resolvers, prior counts). Hand-written: alert texts and the regex matchers for fix/root-cause concepts. Model output was never an input. `frozen.json` holds sha256 of `scoring.py`, `cases.json`, `ground_truth.json`, `build_data.py`; `run.py` refuses to run if they change. Collection and scoring are separate phases.
- **N/A rule:** failed-fix warning, evidence retrieval, resolver knowledge and recurrence detection need history, so Stateless is **N/A, not 0**. (Stateless incidentally warned against a known failed fix in 0 of 7 applicable cases; recorded, never scored.) Failed-fix avoidance applies only to the 7 cases whose seed pattern has a failed fix.
- **Win/tie/loss:** mean of metrics applicable to both conditions (specific root cause, worked fix in any of 3 actions, failed-fix avoidance, zero unsupported claims, actionability/3). Tie if |A−B| ≤ 0.10.

## Headline results (frozen scoring)

| Metric | A Stateless | B RecallOps |
|---|---|---|
| Root cause, generic (coarse category) | 14/15 | 15/15 |
| **Root cause, known (specific to seed history)** | **1/15** | **13/15** |
| **Historically successful fix in any of 3 actions** | 10/15 | 15/15 |
| Successful fix as first action | 1/15 | 15/15 |
| **Failed-fix avoidance** (7 applicable) | **1/7** | **7/7** |
| Failed-fix warning (7 applicable) | N/A | 7/7 (all via the structured warning) |
| Recurrence detected | N/A | 15/15; occurrence number exact 15/15 |
| Evidence retrieval: recall / precision / top-1 expected | N/A | 0.89 / 0.79 / 15 of 15 |
| Resolver knowledge (team hint names a true resolver) | N/A | 15/15 |
| Unsupported historical claims (responses with ≥1) | 0/15 | 0/15 |
| Actionability 0–3 (mean, **see caveat**) | 0.93 | 2.13 |
| Latency median / p95 / max | 4.07s / 5.41s / 6.19s | 8.99s / 15.31s / 18.67s |
| Composite (shared metrics, mean) | 0.469 | 0.904 |
| **Per-case verdicts** | stateless wins **0** | RecallOps wins **15**, ties **0** |

Subsets: demo-tuned C01–C05: A 0.477 vs B 0.840; authored C06–C15: A 0.465 vs B 0.937. RecallOps won all cases in both subsets.

## Per-case (composite A / B · specific RC A/B · worked fix A/B · evidence recall/precision · retrieved IDs · latency A/B)

| Case | Pattern | A | B | Verdict | RC | Fix | Evid R/P (retrieved) | Lat (s) |
|---|---|---|---|---|---|---|---|---|
| C01 | postgres_pool_exhaustion | 0.47 | 0.73 | recallops | 0/0 | 1/1 | 1.00/1.00 (002,021,009,017) | 2.3/3.3 |
| C02 | postgres_pool_exhaustion | 0.53 | 0.93 | recallops | 0/1 | 1/1 | 1.00/1.00 | 1.4/3.2 |
| C03 | redis_oom | 0.25 | 0.67 | recallops | 0/0 | 0/1 | 0.67/0.67 (003,008,016) | 4.4/7.2 |
| C04 | kafka_consumer_lag | 0.67 | 0.93 | recallops | 0/1 | 1/1 | 1.00/1.00 | 6.2/7.3 |
| C05 | postgres_pool_exhaustion | 0.47 | 0.93 | recallops | 0/1 | 1/1 | 1.00/1.00 | 5.1/10.7 |
| C06 | postgres_pool_exhaustion | 0.53 | 0.93 | recallops | 0/1 | 1/1 | **0.50/0.50** (002,016,009,012) | 1.8/13.9 |
| C07 | redis_oom | 0.50 | 0.92 | recallops | 0/1 | 1/1 | 0.67/1.00 (003,019,008) | 4.1/18.7 |
| C08 | kafka_consumer_lag | 0.33 | 1.00 | recallops | 0/1 | 0/1 | 0.50/1.00 (006 only) | 3.3/9.1 |
| C09 | tls_cert_expired | 0.53 | 0.93 | recallops | 0/1 | 1/1 | 1.00/0.33 | 5.1/8.5 |
| C10 | redis_oom_session_store | 0.50 | 0.92 | recallops | 0/1 | 1/1 | 1.00/1.00 | 3.3/10.1 |
| C11 | k8s_oom_killed_memory_leak | 0.58 | 0.92 | recallops | 0/1 | 1/1 | 1.00/1.00 | 4.1/6.1 |
| C12 | search_slow_query_missing_index | 0.50 | 0.92 | recallops | 0/1 | 1/1 | 1.00/1.00 | 4.5/9.0 |
| C13 | opensearch_shard_allocation_failed | 0.25 | 0.92 | recallops | 0/1 | 0/1 | 1.00/0.17 (6 hits, 5 unrelated) | 3.3/13.2 |
| C14 | bad_feature_flag_regression | 0.58 | 0.92 | recallops | 1/1 | 0/1 | 1.00/1.00 | 4.4/7.2 |
| C15 | webhook_signature_mismatch | 0.33 | 1.00 | recallops | 0/1 | 0/1 | 1.00/0.17 (6 hits, 5 unrelated) | 3.4/11.4 |

Raw prompts, model text, structured pipeline output and timings for every call are in `raw/C01.json` … `raw/C15.json`; run metadata in `raw/_meta.json`; per-case scores in `results.json`.

## Audit findings (read before quoting any number)

I read raw outputs after scoring. The frozen scorer was **not** changed. `posthoc_audit.json` / `posthoc_audit.py` hold sensitivity checks and are explicitly post-hoc.

1. **Actionability is not a valid win.** 41 of RecallOps' 45 `first_actions` are bare fix-type labels (`increase_postgres_pool_size`, `kill_idle_db_connections`, …), because the production guard forces `first_actions[0]` to contain the top-ranked fix type and the model echoes labels. My frozen "specific artifact" regex matches snake_case tokens, so it credited them. Counting label-only actions as non-prose, actionability is **A 0.93 vs B 0.33**, the reverse of the headline, and the composite still favors RecallOps in 15/15 cases (A 0.469 vs B 0.769). Honest reading: RecallOps' actions are the *right* concrete levers but terse and unreadable as instructions; Stateless prose is fluent but mostly "check/inspect/review" (only 1 of 15 first actions was a real mitigation that matched a historical fix). **Actionability: scorer-dependent, do not claim a win.** This is also a product finding.
2. **Two scorer errors against RecallOps, one in its favor, one against Stateless (hand-adjudicated, see `posthoc_audit.json`):** C01 B root cause is a true hit (says "never releases", my regex wanted "released"); C09 A "renew the cert, then restart" is scored as recommending the failed pod restart, harsh on Stateless; C14 A root cause credited loosely. Adjudicated: known root cause B 14/15, A 0/15; failed-fix avoided A 2/7, B 7/7. Conclusions do not change.
3. **Real RecallOps weaknesses (kept in, not tuned):**
   - **C03** (redis_oom): top hits INC-003/008/016, missed INC-015, so the root cause cited is the old "no eviction policy" instead of the TTL key-prefix mismatch found in INC-015 — the stale-diagnosis risk of recall-by-similarity.
   - **C06**: on a paraphrased alert (HikariPool wording instead of the Postgres error text), retrieval fell to recall 0.50 and pulled INC-016/INC-012 (unrelated); the answer was still right because the ranked fixes came from INC-002's pool.
   - **C13, C15**: evidence precision 0.17: 5 of 6 evidence incidents were unrelated noise (relevance floor keeps weak neighbours). C08 recalled only 1 of 2 sibling incidents.
   - **Latency:** B is ~2.2× slower (median 9.0s vs 4.1s; p95 15.3s), includes Hindsight recall on a shared, contended Groq key.
4. **Where Stateless is fine:** it identified the generic failure category 14/15 (B 15/15), and got a historically-working fix into its 3 actions in 10/15 (mostly generic best practice: scale consumers, renew cert, reduce flag rollout). The gap is concentrated in (a) the *known* root cause, (b) putting the proven fix first, and (c) avoiding the historically failed fix (rollback on pool exhaustion, adding partitions on Kafka lag, restart on cert expiry).
5. **Unsupported claims tie at 0/15 vs 0/15.** Stateless was not tempted to invent history, and B's post-validation guard held (no ID outside recall). This benchmark shows no hallucination difference; it does not show memory reduces hallucination.

## Limitations

- n=15, one run each, one model, temperature 0.2 – no confidence intervals; single-sample noise not measured.
- **Retrieval is easy here:** every case is a new occurrence of a pattern already in memory, and for single-incident patterns (C09–C15) the original incident is the memory. There is **no unseen-incident control** and no held-out split. Results show what memory adds *when the history exists*, not how RecallOps behaves on genuinely novel incidents. C01–C05 are additionally the alerts production was calibrated on.
- Same author wrote the alert texts and the regex matchers; regex scoring is a proxy (three known misjudgements above), and the actionability rubric is weak (finding 1).
- Stateless prompt is my own fair-baseline prompt, not `/compare`'s "generic checklist" baseline (which would make the gap look larger).
- B's per-case evidence is read from a live shared Hindsight bank at run time; other agents were active concurrently (2 rate-limit retries observed).
- Latency contains contention from the other agents' Groq/Hindsight use.

## Files

`cases.json`, `ground_truth.json`, `build_data.py`, `scoring.py`, `test_scoring_synthetic.py` (synthetic-string checks only), `freeze.py`, `frozen.json`, `run.py`, `raw/`, `results.json`, `posthoc_audit.py`, `posthoc_audit.json`, `head_sha.txt`, `report.md`, `presentation_claims.md`.

Reproduce: `../../backend/.venv/Scripts/python.exe run.py collect && ... run.py score` (collect calls Groq + Hindsight, read-only against Hindsight).
