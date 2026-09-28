from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import ledger, memory
from app.config import get_settings
from app.models import HealthResponse
from app.routes import alert, briefing, compare, demo_alerts, feedback, incidents as incidents_routes, metrics, reset, resolve, seed

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # get_client() is an lru_cache singleton meant to live for one app lifespan. Clear
    # the cache on startup too, not just close on shutdown -- otherwise a second
    # `with TestClient(app) as c:` lifecycle in the same process (e.g. a different test
    # module's fixture) would reuse the previous lifespan's now-closed client instance
    # and every Hindsight call would fail with "Session is closed".
    memory.get_client.cache_clear()
    ledger.ensure_fresh()
    yield
    await memory.get_client().aclose()


app = FastAPI(title="RecallOps API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
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


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    memory_status, _elapsed = await memory.ping()
    return HealthResponse(status="ok", memory=memory_status)
