from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

from app.models import Alert, DemoAlertOut

router = APIRouter()
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


@router.get("/demo-alerts", response_model=list[DemoAlertOut])
async def get_demo_alerts() -> list[DemoAlertOut]:
    demo_alerts = json.loads((DATA_DIR / "demo_alerts.json").read_text(encoding="utf-8"))
    out = []
    for demo in demo_alerts:
        alert = Alert(
            service=demo["service"],
            severity=demo["severity"],
            title=demo["title"],
            symptoms=demo.get("symptoms"),
            error_message=demo["error_message"],
            log_snippet=demo["log_snippet"],
            error_signature=demo.get("error_signature"),
            submitted_at=demo.get("submitted_at"),
        )
        out.append(DemoAlertOut(alert_id=demo["alert_id"], target_capability=demo["target_capability"], title=demo["title"], alert=alert))
    return out
