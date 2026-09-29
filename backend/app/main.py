from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import ledger, memory, security, seeding
from app.config import get_settings, is_production
from app.models import HealthResponse
from app.routes import alert, briefing, chat, compare, demo_alerts, feedback, incidents as incidents_routes, insights, metrics, reset, resolve, seed

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # get_client() is an lru_cache singleton meant to live for one app lifespan. Clear
    # the cache on startup too, not just close on shutdown -- otherwise a second
    # `with TestClient(app) as c:` lifecycle in the same process (e.g. a different test
    # module's fixture) would reuse the previous lifespan's now-closed client instance
    # and every Hindsight call would fail with "Session is closed".
    security.startup_warnings()  # names only, never key values
    memory.get_client.cache_clear()
    await memory.ensure_banks()
    ledger.ensure_fresh()
    insights.invalidate()  # kick off reflect; if the bank turns out empty below, the
    # auto-seed's own completion invalidates (and so re-reflects) again once seeded.
    seeding.start_auto_seed_if_empty()  # never blocks startup -- see app/seeding.py
    yield
    await memory.get_client().aclose()


# Interactive docs and the OpenAPI schema are disabled when APP_ENV=production.
_docs = {"docs_url": None, "redoc_url": None, "openapi_url": None} if is_production() else {}
app = FastAPI(title="RecallOps API", lifespan=lifespan, **_docs)

# Added BEFORE CORS so CORS is outermost and 401/413/429 responses still carry CORS headers.
# CORS is not authentication; see app/security.py.
app.add_middleware(security.SecurityMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(seed.router)
app.include_router(reset.router)
app.include_router(alert.router)
app.include_router(briefing.router)
app.include_router(feedback.router)
app.include_router(resolve.router)
app.include_router(demo_alerts.router)
app.include_router(incidents_routes.router)
app.include_router(compare.router)
app.include_router(metrics.router)
app.include_router(insights.router)
app.include_router(chat.router)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    memory_status, _elapsed = await memory.ping()
    return HealthResponse(status="ok", memory=memory_status, seeding=seeding.is_seeding())
