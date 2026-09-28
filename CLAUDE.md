# RecallOps

Incident response agent that learns from every outage, built on Hindsight memory. See `docs/SPEC.md`
(and the source PDF next to it) for the full product spec — capabilities, memory design, scoring
formula, demo script. `docs/PROMPTS.md` has the build sequence this project follows, prompt by prompt.

## Stack

- **Backend**: Python, FastAPI
- **Frontend**: React + Tailwind, charts via Recharts
- **Memory**: Hindsight Cloud, via the `hindsight-client` PyPI package (`hindsight_client.Hindsight`)
- **LLM**: Groq, primary model `openai/gpt-oss-120b`, fallback `qwen/qwen3.8-27b` (see `.env.example`
  for the exact model strings — `LLM_MODEL_PRIMARY` / `LLM_MODEL_FALLBACK`)

## Rules

- **One logical change per commit.** Don't bundle unrelated work into a single commit.
- **Never guess the Hindsight API.** Read the installed `hindsight_client` package (introspect it,
  don't assume method signatures) or the official docs before writing a call. When you use a new
  Hindsight call for the first time, tell the user which calls you used and where you confirmed the
  signature.
- **All LLM calls go through one wrapper in `backend/app/llm.py`.** The wrapper: retries transient
  failures, strips any reasoning/thinking text from the response before returning it, repairs/parses
  JSON when structured output is expected, then falls back to `LLM_MODEL_FALLBACK` if the primary
  model still fails. No other module calls Groq directly.
- **Briefings may cite only incident IDs returned by `recall`.** Post-validate any LLM-generated
  briefing against the set of incident IDs actually present in the recall results before returning it
  to the client. Never let the model cite an ID it invented.
- **Mask secrets before any `retain`.** Scrub API keys, tokens, passwords, and similar sensitive
  values out of content before it is written to Hindsight memory.
- **All config comes from `.env`.** See `.env.example` for the required keys. Never print or log key
  values (not to stdout, not in error messages, not in committed files).

## Repo layout

- `backend/app/` — FastAPI app (`main.py`, `models.py`, `memory.py`, `llm.py`, `scoring.py`,
  `briefing.py`), routes in `backend/app/routes/`
- `backend/tests/` — pytest
- `backend/data/` — seed data (incidents, team, demo alerts, metrics)
- `scripts/` — standalone scripts (smoke tests, seed validation, etc.)
- `frontend/` — React + Tailwind app
