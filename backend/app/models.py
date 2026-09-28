"""Pydantic response models. Shapes come from docs/API_CONTRACT.md exactly -- it is the
only source of truth for request/response shapes (docs/AGENTS.md). If a shape here needs
to change, log it in docs/CONTRACT_ISSUES.md under "## From A" instead of inventing a
field.

Only the models needed so far (health/seed/reset) are defined. The rest (Alert,
Evidence, RankedFix, ...) land with the routes that use them in a later prompt.
"""
from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]
    memory: Literal["ok", "slow", "down"]


class SeedResponse(BaseModel):
    seeded: int
    duration_s: float


class ResetResponse(BaseModel):
    ok: bool
