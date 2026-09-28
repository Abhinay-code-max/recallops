from fastapi import APIRouter

from app import seeding
from app.models import SeedResponse

router = APIRouter()


@router.post("/seed", response_model=SeedResponse)
async def seed() -> SeedResponse:
    """Idempotent: safe to call repeatedly (stable document_ids, update_mode="replace")."""
    result = await seeding.run_seed()
    return SeedResponse(seeded=result.seeded, duration_s=result.duration_s)
