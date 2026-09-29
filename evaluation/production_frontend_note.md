# Production frontend note (user-supplied, not verified by these artifacts)

The reliability track (`reliability/production_health.md` §4, `reliability/final_report.md`) states that no production frontend URL could be determined from repository configuration or git metadata, and therefore did not test one. That was accurate for what that track could see.

The project owner subsequently supplied the following production deployment details at commit time:

| Item | Value | Status |
|---|---|---|
| Production frontend | https://recallops-psi.vercel.app | Reported by the owner |
| Production backend | https://recallops-8ich.onrender.com | Health checked in `reliability/production_health.md` |
| Frontend loads | PASS | Owner-reported |
| Frontend → backend calls | PASS | Owner-reported |
| CORS | PASS | Owner-reported |
| Browser console errors | 0 | Owner-reported |

**Provenance:** the frontend rows above were NOT verified by any experiment in `evaluation/`, and the auditing agent did not re-test them. No raw evidence for them is committed here. Treat them as claims until backed by an artifact.

**Other clarifications recorded at commit time**
- Live suite: 78 passed, 2 failed (documented in `reliability/regression.md`). It is not "all tests passed".
- `reliability/demo_flow.md` records `kill_idle_db_connections` as *failed* in the demo-flow run; the `learning/` experiment used a separate, controlled feedback of *worked*. They are different runs.
- `reliability/regression.md` and `reliability/demo_flow.md` contain local file paths and an operator name; left unchanged to preserve the artifacts as produced.
