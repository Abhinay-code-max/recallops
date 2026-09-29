# RecallOps

The incident response agent that learns from every outage. Built on Hindsight memory for
HackwithHyderabad 3.0. See `docs/SPEC.md` for the full build specification.

- **Frontend:** https://recallops-psi.vercel.app
- **Backend API:** https://recallops-8ich.onrender.com (`GET /health`)

## The problem

On-call engineers re-debug outages their team has already solved: the same Friday-deploy pool
exhaustion, the same Monday Redis OOM, the same failed rollback. The knowledge lives in old
tickets and in the head of whoever fixed it last.

## What it does

When an alert arrives, RecallOps recalls similar past incidents from Hindsight memory and returns:

- **Evidence** — the matching past incidents (IDs, dates, services).
- **Ranked fixes** — scored from the fix-outcome ledger (what worked, partly worked, or failed).
- **Failed-fix warnings** — e.g. "rollback failed 2 of 2 times for this pattern".
- **Recurrence detection** — "occurrence #5 of this pattern", with open permanent fixes flagged.
- **Team hint** — who resolved this pattern before.
- **A triage briefing** — root cause, blast radius, first actions. The LLM may cite only incident
  IDs that recall actually returned; anything else is rejected and the briefing falls back to a
  template.

Engineer feedback (`POST /feedback`) and resolutions/postmortems (`POST /resolve`) are retained
back into memory, so later alerts see them. Ranking is a deterministic Python formula over the
ledger counts and recalled similarity; **no LLM is retrained**.

## Architecture

```
alert ──> FastAPI ──> Hindsight recall (incidents + live banks)
                        ├─> ledger + scoring.py  -> ranked fixes, warnings, recurrence, team hint
                        └─> llm.py (Groq)        -> briefing (citation + grounding guards)
feedback / resolve ──> Hindsight retain (secrets masked first) ──> future recall
```

- **Backend:** Python, FastAPI (`backend/app/`)
- **Frontend:** React + Tailwind, Recharts (`frontend/`)
- **Memory:** Hindsight Cloud via `hindsight-client` — banks `incidents`, `fix-outcomes`, `team`,
  `baseline` (always empty, for the no-memory comparison) and `recallops-live` (runtime writes)
- **LLM:** Groq, `openai/gpt-oss-120b` primary, `qwen/qwen3.8-27b` fallback. Every call goes
  through `backend/app/llm.py` (retries, reasoning stripped, JSON repair, fallback, never raises)
- **Hindsight notes:** verified behaviours and signatures in `docs/HINDSIGHT_NOTES.md`

Main endpoints: `POST /alert`, `GET /incidents/{id}/briefing/stream` (SSE), `POST /compare`,
`POST /feedback`, `POST /resolve`, `POST /chat`, `GET /incidents`, `GET /insights`, `GET /metrics`,
`GET /demo-alerts`, `POST /seed`, `POST /reset`, `GET /health`. See `docs/API_CONTRACT.md`.

## Repo layout

- `backend/` — FastAPI app (`app/`), tests (`tests/`), seed data (`data/`)
- `frontend/` — React + Tailwind UI
- `scripts/` — standalone scripts (Hindsight smoke test, seed validation, demo flow, etc.)
- `docs/` — spec, API contract, Hindsight notes, build prompts
- `evaluation/` — benchmark, learning and reliability experiments (see below)

## Setup

### Backend

```bash
cd backend
python -m venv .venv
./.venv/Scripts/pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # macOS/Linux
cp ../.env.example ../.env   # fill in HINDSIGHT_*, GROQ_API_KEY, FRONTEND_ORIGIN
./.venv/Scripts/python -m uvicorn app.main:app --reload
```

`GET /health` should return `{"status": "ok", ...}`. On first start with an empty Hindsight bank
the app seeds the demo incidents in the background. Never commit `.env`.

### Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, API base from VITE_API_BASE (default http://localhost:8000)
npm run build      # tsc -b && vite build
```

### Tests

```bash
powershell -File scripts/run_tests.ps1          # offline tests only (default)
powershell -File scripts/run_tests.ps1 -Live    # also hits real Hindsight and Groq
```

### Hindsight smoke test

```bash
cd backend
./.venv/Scripts/python ../scripts/hindsight_smoke.py
```

Creates a bank, retains one item with metadata, recalls it, runs reflect, and prints the raw
responses.

## Evaluation

Three independent tracks live under `evaluation/`, each with its own report. Baseline commit
evaluated: `05eb0cb`.

### 1. Memory vs stateless (`evaluation/benchmark/`)

15 cases across 10 incident patterns; the **same model** (`openai/gpt-oss-120b`) with and without
RecallOps memory. Scoring was frozen by hash before any output was seen.

| Metric | Stateless | RecallOps |
|---|---|---|
| Known root cause (frozen automated scorer) | 1/15 | 13/15 |
| Known root cause (manual audit) | 0/15 | 14/15 |
| Successful fix in top 3 actions | 10/15 | 15/15 |
| Successful fix as first action | 1/15 | 15/15 |
| Failed-fix avoidance (7 applicable cases) | 1/7 | 7/7 |
| Failed-fix warning | N/A | 7/7 |
| Recurrence detection | N/A | 15/15 |
| Expected incident retrieved first | N/A | 15/15 |
| Unsupported historical claims | 0/15 | 0/15 |
| Median / p95 latency | 4.07s / 5.41s | 8.99s / 15.31s |

Caveats (details in `evaluation/benchmark/report.md`):

- **Actionability is not a valid comparison.** The scorer credited RecallOps' bare fix-type labels
  (e.g. `increase_postgres_pool_size`), so that metric is unreliable and is not claimed.
- Every case is a new occurrence of a pattern already in memory; there is **no novel-incident
  control**. The five demo alerts were also used to calibrate production.
- n = 15, one run per case, one model. No hallucination difference was observed (0 vs 0).
- Retrieval is imperfect: one paraphrased alert dropped to 50% recall, and two cases returned
  mostly unrelated evidence.

### 2. Feedback learning (`evaluation/learning/`)

A controlled test on `payments-api / postgres_pool_exhaustion`: feedback `kill_idle_db_connections
→ worked` immediately moved that fix from score 0.4358 → 0.7000, rank 2 → 1, worked count 1 → 2.
On the *next* related incident the feedback was still counted, but the final rank stayed #2
because recalled similarity differed, so the top recommendation did **not** change. The postmortem
was retained and became available to future recall. No LLM retraining occurred.

### 3. Reliability (`evaluation/reliability/`)

- Offline regression: 45 passed, 0 failed, 35 deselected. Frontend build: pass.
- Demo flow: 11/11 stages. API contract, SSE, deduplication, Hindsight-degraded and Groq-degraded
  modes, and security checks: pass.
- The broader live suite was **78 passed, 2 failed** (reasons documented in `regression.md`);
  it is not "all tests passed".
- Production frontend/CORS/console results are owner-reported and not verified by these
  artifacts: see `evaluation/production_frontend_note.md`.

## Security (production hardening)

Set `APP_ENV=production` on the server. This disables `/docs`, `/redoc` and `/openapi.json` and turns on
hardened mode (also enabled whenever `ADMIN_API_KEY` or `INGEST_API_KEY` is set). Local development stays open.

| Endpoint | Protection |
|---|---|
| `POST /seed`, `POST /reset` | `ADMIN_API_KEY` in the `X-RecallOps-Key` header (fails closed if unset in production); 5/min per IP |
| `POST /alert` | `INGEST_API_KEY` (or the admin key), **or** content that exactly matches a predefined demo alert, which is replaced by the server's copy; 10/min per IP |
| `POST /feedback`, `POST /resolve` | `ADMIN_API_KEY` (an ingest-only key is rejected), plus live incidents only, known fix types, 12 feedback per incident, resolve once |
| `POST /chat`, `POST /compare`, briefing stream | Public, rate limited, input length limits |

Request bodies are capped at 64 KB and text fields have length limits (422 when exceeded). Keys live only in
server env vars: **never** put them in `VITE_*` or the frontend bundle. An operator can use the UI's Seed/Reset
buttons, feedback, resolve or custom alerts by running `sessionStorage.setItem('recallops_key', '<key>')` in the browser console.
Keep `RATE_LIMIT_TRUSTED_HOPS=0` (default) unless the proxy chain in front of the app has been independently
verified; otherwise callers can forge `X-Forwarded-For` to dodge per-IP limits. Global limits always apply. Rate
limits are per process, request bodies are counted by bytes actually received, and there is no user authentication.

## Configuration

All config comes from `.env` (see `.env.example`): `HINDSIGHT_API_KEY`, `HINDSIGHT_BASE_URL`,
`GROQ_API_KEY`, `LLM_MODEL_PRIMARY`, `LLM_MODEL_FALLBACK`, timeouts, and `FRONTEND_ORIGIN`
(comma-separated CORS origins). The backend deploys to Render via `render.yaml`.
