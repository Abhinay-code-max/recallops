from fastapi import APIRouter

from app import seeding
from app.models import ResetResponse

router = APIRouter()


@router.post("/reset", response_model=ResetResponse)
async def reset() -> ResetResponse:
    """Returns memory to freshly-seeded state: deletes and recreates recallops-live only
    (the seeded banks are untouched -- there's no per-document delete to wipe just the
    live memories out of a shared bank, see docs/HINDSIGHT_NOTES.md point 3)."""
    await seeding.run_reset()
    return ResetResponse(ok=True)
