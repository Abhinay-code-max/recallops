# RecallOps Feedback Learning / Adaptation Experiment

## Executive result

RecallOps incorporated one legitimate engineer feedback event without retraining an LLM. The reported fix, `kill_idle_db_connections`, changed from Worked=1 to Worked=2. On the unchanged baseline incident context, the feedback response moved it from rank 2 / score 0.4358 to rank 1 / score 0.7000 (+0.2642). On the next similar incident it ranked 2 / score 0.4338 because the new query produced different recall similarities; the top recommendation therefore did **not** change in the required next-incident comparison. No extra feedback was submitted to force a favorable outcome.

## 1. HEAD evaluated

`05eb0cb325925f03e7395a9d353f7e1d2ea4f732`

Run time: 2026-09-29T06:25:39Z–2026-09-29T06:25:57Z (UTC).

## 2–3. Pattern selected and rationale

Pattern: `payments-api` / `postgres_pool_exhaustion`.

This is the strongest existing controlled pattern: four historical incidents (`INC-002`, `INC-009`, `INC-017`, `INC-021`), four competing mitigations, and all three outcome classes. Historical results include pool resize (Worked 3), kill idle connections (Worked 1, Partial 1), pod restart (Partial 1), and rollback (Failed 2). The project already provides sequential matching demo alerts, so no favorable scenario was invented.

## 4. BEFORE ranked fixes

Baseline request created `INC-023` from existing `DEMO-1`. Recall was not degraded.

| Rank | Fix | Score | Similarity | Worked | Partial | Failed | Recent failures |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `increase_postgres_pool_size` | 0.6598 | 0.8248 | 3 | 0 | 0 | 0 |
| 2 | `kill_idle_db_connections` | 0.4358 | 0.6973 | 1 | 1 | 0 | 0 |
| 3 | `restart_payments_pods` | 0.4124 | 0.8248 | 0 | 1 | 0 | 0 |
| 4 | `rollback_to_previous_deploy` | -0.0938 | 0.8248 | 0 | 0 | 2 | 1 |

Evidence IDs: `INC-002`, `INC-021`, `INC-009`, `INC-017`.

Warnings: failed rollback (2/2), recurrence #5 (~35 days), and permanent fix from `INC-021` still open. Top recommendation: `increase_postgres_pool_size`.

## 5. Feedback submitted

Exactly one `POST /feedback` event:

- Incident: `INC-023`
- Fix: `kill_idle_db_connections`
- Outcome: `worked`
- Notes: “Engineer observed that terminating idle leaked sessions restored checkout capacity for this recurrence.”
- Request sent: `2026-09-29T06:25:39.824194Z`
- Response received: `2026-09-29T06:25:43.068842Z`
- Memories stored: 1

The API does not expose its internal retain timestamp. The two exact client timestamps above bound that server-side event; this limitation is recorded rather than claiming unavailable precision.

On the same incident context, the response immediately changed `kill_idle_db_connections` from score 0.4358 / rank 2 / Worked 1 to score 0.7000 / rank 1 / Worked 2. This same-query comparison isolates the direct feedback effect from query-dependent similarity.

## 6. AFTER ranked fixes

The next existing equivalent alert (`DEMO-2`) created `INC-024`. Recall was not degraded.

| Rank | Fix | Score | Similarity | Worked | Partial | Failed | Recent failures |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `increase_postgres_pool_size` | 0.5330 | 0.6662 | 3 | 0 | 0 | 0 |
| 2 | `kill_idle_db_connections` | 0.4338 | 0.6197 | 2 | 1 | 0 | 0 |
| 3 | `restart_payments_pods` | 0.3331 | 0.6662 | 0 | 1 | 0 | 0 |
| 4 | `rollback_to_previous_deploy` | 0.1666 | 0.6662 | 0 | 0 | 2 | 0 |

Evidence IDs: `INC-002`, `INC-021`, `INC-009`, `INC-017`, `INC-023`. Top recommendation remained `increase_postgres_pool_size`.

## 7–10. Exact deltas, ranks, counts, and warnings

| Fix | Score before | Score after | Delta | Rank before→after | Worked Δ | Partial Δ | Failed Δ | Fix warning before→after |
|---|---:|---:|---:|---|---:|---:|---:|---|
| `increase_postgres_pool_size` | 0.6598 | 0.5330 | -0.1268 | 1→1 | 0 | 0 | 0 | no→no |
| `kill_idle_db_connections` | 0.4358 | 0.4338 | -0.0020 | 2→2 | **+1** | 0 | 0 | no→no |
| `restart_payments_pods` | 0.4124 | 0.3331 | -0.0793 | 3→3 | 0 | 0 | 0 | no→no |
| `rollback_to_previous_deploy` | -0.0938 | 0.1666 | +0.2604 | 4→4 | 0 | 0 | 0 | yes→yes |

Ranks and top recommendation did not change on the next incident. The feedback-affected fix’s score was nearly flat despite its positive count change because its recalled similarity fell from 0.6973 to 0.6197 on the different alert query. Rollback’s score rose because it left the two-incident recent-failure window; its 2 Failed count and failed-fix warning remained unchanged.

Warning kinds remained `failed_fix`, `recurrence`, and `open_permanent_fix`. Only recurrence content changed: occurrence #5 / 35.0 days became #6 / 29.8 days and added `INC-023`. Thus fix-risk warning behavior did not change; recurrence state did.

## 11–13. Evidence, top recommendation, and retention

Evidence changed by adding the just-observed `INC-023`; no prior evidence IDs disappeared. `increase_postgres_pool_size` remained the next incident’s top recommendation.

After the comparison was complete, `INC-024` was resolved once through `/resolve`. A subsequent read-only merged recall for the existing `DEMO-5` pattern returned `INC-024` with relevance 1.0097723707536375 and outcome metadata `worked`. Resolution response reported one memory stored. Therefore the new incident/postmortem was retained and available as future operational memory.

## 14–15. Mechanism and confirmation of no LLM training

The observed adaptation is supported by source code as follows:

1. `/feedback` records the event in the in-process live feedback overlay and appends the fix attempt (`backend/app/incidents.py`, `record_feedback`).
2. It also retains a natural-language feedback memory in the `recallops-live` Hindsight bank (`backend/app/routes/feedback.py`).
3. Exact Worked/Partial/Failed counts come from the structured ledger merged with `_live_feedback`, not from an LLM (`backend/app/ledger.py`, `counts_for_signature`; `backend/app/incidents.py`, `ledger_counts_for`).
4. Ranking is a deterministic Python calculation: `similarity * (worked + 0.5*partial + 1) / (attempts + 2) - 0.3*recent_failures` (`backend/app/scoring.py`).
5. `/resolve` retains `live-postmortem-INC-024` in the same live memory bank (`backend/app/routes/resolve.py`).

The code does call an LLM to draft briefings/postmortems, with a deterministic postmortem fallback, but no training, fine-tuning, optimizer, backpropagation, or weight-update path is present in the inspected application. The demonstrated recommendation changes arise from retrieved Hindsight/live outcome memory, exact ledger counts, and deterministic scoring. The experiment makes no broader claim about the internals of the external hosted models.

## 16. Generated files

- `before.json` — complete baseline request, response, evidence, scores, warnings, and recurrence
- `feedback.json` — the sole feedback request/response and timestamps
- `after.json` — complete next-incident request and response
- `delta.json` — exact before/after deltas plus same-query immediate feedback effect
- `resolution.json` — post-comparison resolution/postmortem retention request and response
- `retention.json` — read-only future recall result
- `run_manifest.json` — HEAD, incident IDs, and run summary
- `run_experiment.py` — reproducible one-shot harness (must not be rerun without first treating it as a new experiment because it submits feedback)
- `learning_report.md` — this report
- `judge_demo.md` — under-60-second judge script

## 17. Failures and limitations

- A background insights `reflect(incidents)` task logged a `ServerDisconnectedError` and fell back with `MemoryUnavailableError`. It is separate from the alert recall/ranking/feedback path. Both alert responses and the final retention recall reported `degraded: false`.
- The server-side feedback retain timestamp is not returned by the API; exact request/response bounds are recorded.
- Scores across the two incidents combine count changes with query-dependent similarity changes. The immediate same-query feedback response is included to isolate the direct adaptation.
- The rank order did not change on the required next incident, and no additional feedback was submitted to manipulate it.

## 18–20. Repository and delivery confirmation

`git diff -- evaluation/learning/` is empty because all evaluation files are new and untracked; Git does not show untracked files in a normal diff. `git status --short` reports `?? evaluation/` (and the pre-existing unrelated `?? linkedin-screenshots/`).

`git diff -- backend frontend docs scripts` is empty. Application source, seed data, ranking formula, and production prompts were untouched. Nothing was staged, committed, pushed, or deployed.
