# RecallOps

The incident response agent that learns from every outage. Built on Hindsight memory for
HackwithHyderabad 3.0. See `docs/SPEC.md` for the full build specification.

> Scaffolding stage — features land per `docs/PROMPTS.md`. This stub will grow into the
> problem statement, architecture diagram, Hindsight usage section, setup steps, and
> screenshots required by the submission checklist (spec section 11).

## Repo layout

- `backend/` — FastAPI app (`app/`), tests (`tests/`), seed data (`data/`)
- `frontend/` — React + Tailwind UI
- `scripts/` — standalone scripts (Hindsight smoke test, seed validation, etc.)
- `docs/` — spec and build prompts

## Backend setup

```bash
cd backend
python -m venv .venv
./.venv/Scripts/pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # macOS/Linux
cp ../.env.example ../.env   # fill in HINDSIGHT_* and GROQ_API_KEY
./.venv/Scripts/python -m uvicorn app.main:app --reload --app-dir backend
```

`GET /health` should return `{"status": "ok"}`.

## Hindsight smoke test

```bash
cd backend
./.venv/Scripts/python ../scripts/hindsight_smoke.py
```

Creates a bank, retains one item with metadata, recalls it, runs reflect, and prints the raw
responses.
