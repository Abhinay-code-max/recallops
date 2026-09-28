# RecallOps: Claude Code prompts

Run in order. After each prompt, run the review gate and paste the output back for review before continuing.
Repo rules live in CLAUDE.md (created by Prompt 0).

---

## Prompt 0: Foundation and Hindsight smoke test

```
Read docs/SPEC.md (the PDF next to it is the source of truth). Don't build features yet.
1. Create CLAUDE.md with the stack (FastAPI, React+Tailwind+Recharts, Hindsight Cloud, Groq gpt-oss-120b with qwen3-32b fallback) and these rules:
- One logical change per commit.
- Never guess the Hindsight API. Read the installed package/docs and tell me which calls you used.
- All LLM calls go through one wrapper in llm.py: retry, JSON repair, then fallback model.
- Briefings may cite only incident IDs returned by recall.
- Mask secrets before any retain.
- All config comes from .env (see .env.example).
2. Scaffold backend/app/{main,models,memory,llm,scoring,briefing}.py, backend/app/routes/, backend/tests/, backend/data/, frontend/, README stub.
3. Add GET /health and scripts/hindsight_smoke.py: create a bank, retain one item with metadata, recall it, run reflect, print raw responses.
4. Run the smoke script and show me the output. Commit.
```
**Gate:** paste the smoke output. Check that retain, recall and reflect all returned real data, and note what metadata comes back.

---

## Prompt 1: Seed data

```
Generate backend/data/seed_incidents.json, seed_team.json and demo_alerts.json per spec section 6.
- ShipFast, 5 services, 22 incidents over ~4 months ending 2026-09-10, IDs INC-001+, SEV1-3, realistic logs and stack traces.
- Planted patterns: DB pool exhaustion after Friday deploys (4x), Redis OOM on Mondays, Kafka lag during sales, expired TLS cert, bad config flag.
- Each incident has fix_attempts[] with fix_type, outcome (worked/partial/failed), minutes_to_effect, resolver. Include some failed rollbacks for payments-api and one open permanent fix.
- 7 engineers with specialties and preferences.
- 5 held-back demo alerts, one per: recall, failure warning, reflect pattern, team routing, recurring detector.
- Also seed_metrics.json with simulated MTTR/accuracy per incident, trending 47 to 9 min.
Write scripts/validate_seed.py asserting all of this (counts, unique IDs, patterns, each demo alert matches a seed incident). Run it and commit.
```
**Gate:** paste the validator output plus one full incident and one demo alert.

---

## Prompt 2: Memory layer

```
Implement memory.py: banks incidents, fix-outcomes, team, baseline (stays empty).
- retain/recall/reflect wrappers with timeouts and graceful errors.
- Retain carries metadata: service, severity, date, incident_id, outcome.
- Recall returns typed objects with incident_id, date and relevance.
- Secret masking before retain, with tests.
- POST /seed (idempotent) and POST /reset.
Write a script that seeds, then recalls each demo alert and prints the top 3 incident IDs. Commit.
```
**Gate:** paste that script's output. Each demo alert should surface its planted incident.

---

## Prompt 3: Core loop

```
Build POST /alert, /feedback, /resolve.
- Alert: normalise, dedupe within minutes, recall across all three banks, score fixes with the exact spec formula (in scoring.py), stream the briefing over SSE.
- Briefing: root cause, blast radius, first 3 actions, who fixed it last. Post-validate that every cited INC ID came from recall.
- Feedback retains the outcome. Resolve drafts a postmortem and retains it.
- Edge cases: empty memory, no similar incident (say so), conflicting outcomes.
pytest for scoring and the hallucination guard. Commit each piece separately.
```
**Gate:** paste pytest output and curl output for demo alert 1, before and after a Failed feedback. The ranking must visibly change.

---

## Prompt 4: Chat, compare, insights, metrics

```
Add /chat (recall-grounded), /compare (same alert via baseline bank vs memory), /insights (reflect-based patterns, recurring detector, open permanent fixes, team routing) and /metrics (MTTR, accuracy, memories count, incidents handled). Every response includes the evidence list. Tests, then commit.
```
**Gate:** paste /compare and /insights JSON for one alert.

---

## Prompt 5: Frontend

```
Build the React+Tailwind dark ops UI: Live Incident (alert card, streaming briefing, ranked fixes with score numbers, failure warnings, feedback buttons, chat), Memory Evidence panel, Compare split view, Learning dashboard, Pattern Insights, Incident history. Severity colours, monospace logs, loading and error states. Wire everything to the real endpoints, no mocked data. Commit per screen.
```
**Gate:** screenshots of Live Incident, Compare and Dashboard.

---

## Prompt 6: Harden, deploy, docs

```
1. Handle Hindsight-timeout and LLM-failure paths; the UI must never freeze.
2. Write an e2e script that runs the spec section 8 demo sequence against the API and asserts the ranking change.
3. Deploy backend to Render/Railway and frontend to Vercel. Verify /reset and /seed on the live URL.
4. Write the README: problem, architecture diagram, Hindsight usage section (banks, retain/recall/reflect timing, before/after example), setup, .env.example.
```
**Gate:** live URL and e2e output.

---

Cut order if time runs short: E (runbook evolution), then D (deploy-risk), then F (recurring detector). Keep A, B, C.
