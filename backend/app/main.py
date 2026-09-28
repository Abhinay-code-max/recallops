from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import memory
from app.config import get_settings
from app.models import HealthResponse
from app.routes import alert, reset, seed

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
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


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    memory_status, _elapsed = await memory.ping()
    return HealthResponse(status="ok", memory=memory_status)
