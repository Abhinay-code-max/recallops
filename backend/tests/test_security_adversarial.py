"""Adversarial regression tests from the Codex review of d99f198. Offline: fake keys, stubbed I/O.

Fixtures (`isolated`, `prod`) and helpers are shared with test_security.py.
"""
from __future__ import annotations

import asyncio
import importlib
import json

from fastapi.testclient import TestClient

from app import incidents, security

from .test_security import (  # noqa: F401  (fixtures are used by name)
    ADMIN, DEMO, INGEST, admin, demo_payload, isolated, make_live_incident, prod,
)

FEEDBACK_BODY = {"incident_id": "INC-900", "fix_type": "increase_postgres_pool_size", "outcome": "worked"}
RESOLVE_BODY = {"incident_id": "INC-900", "resolver": "Test Engineer"}
LIMIT = security.MAX_BODY_BYTES


async def _run_asgi(frames, headers, path="/chat", method="POST"):
    """Drive SecurityMiddleware with hand-built ASGI frames (no HTTP client can forge false lengths)."""
    seen = {"body": b"", "app_called": False}
    sent = []
    pending = list(frames)

    async def downstream(scope, receive, send):
        seen["app_called"] = True
        while True:
            message = await receive()
            seen["body"] += message.get("body", b"")
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def receive():
        return pending.pop(0) if pending else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": method, "path": path, "headers": headers, "client": ("1.2.3.4", 1)}
    await security.SecurityMiddleware(downstream)(scope, receive, send)
    return next(m["status"] for m in sent if m["type"] == "http.response.start"), seen, pending


def _frames(*sizes):
    return [{"type": "http.request", "body": b"x" * n, "more_body": i < len(sizes) - 1} for i, n in enumerate(sizes)]


# ---------------------------------------------------------------- body limit (actual bytes)
def test_false_content_length_with_oversized_body_gets_413(isolated):
    status, seen, _ = asyncio.run(_run_asgi(_frames(LIMIT + 6000), [(b"content-length", b"1")]))
    assert status == 413 and seen["app_called"] is False


def test_missing_content_length_with_oversized_body_gets_413(isolated):
    status, seen, _ = asyncio.run(_run_asgi(_frames(LIMIT + 1), []))
    assert status == 413 and seen["app_called"] is False


def test_multi_frame_body_crossing_limit_gets_413_and_stops_reading(isolated):
    frames = _frames(*([16 * 1024] * 8))  # 128 KiB in 8 frames, chunked, no content-length
    status, seen, leftover = asyncio.run(_run_asgi(frames, [(b"transfer-encoding", b"chunked")]))
    assert status == 413 and seen["app_called"] is False
    assert len(leftover) >= 3  # frames the middleware never consumed once the limit was crossed


def test_body_below_limit_is_replayed_intact_even_with_false_length(isolated):
    status, seen, _ = asyncio.run(_run_asgi(_frames(20_000, 20_000, 20_000), [(b"content-length", b"1")]))
    assert status == 200 and len(seen["body"]) == 60_000 and seen["app_called"] is True


def test_valid_demo_alert_with_ignored_70kb_field_and_false_length_gets_413(prod):
    big = json.dumps(demo_payload(0, deploy="x" * 70_000)).encode()
    r = prod.post("/alert", content=big, headers={"content-type": "application/json", "content-length": "1"})
    assert r.status_code == 413
    assert prod.post("/alert", json=demo_payload(0)).status_code == 200  # a normal body still works


# ---------------------------------------------------------------- feedback / resolve need the admin key
def test_feedback_requires_admin_key_in_hardened_mode(prod, isolated):
    inc = make_live_incident()
    assert prod.post("/feedback", json=FEEDBACK_BODY).status_code == 401
    assert prod.post("/feedback", json=FEEDBACK_BODY, headers=admin("wrong")).status_code == 401
    assert prod.post("/feedback", json=FEEDBACK_BODY, headers=admin(INGEST)).status_code == 401  # ingest-only is not enough
    assert isolated["retain"] == 0 and incidents.feedback_for(inc) == []
    assert prod.post("/feedback", json=FEEDBACK_BODY, headers=admin(ADMIN)).status_code == 200
    assert len(incidents.feedback_for(inc)) == 1


def test_resolve_requires_admin_key_in_hardened_mode(prod, isolated):
    inc = make_live_incident()
    assert prod.post("/resolve", json=RESOLVE_BODY).status_code == 401
    assert prod.post("/resolve", json=RESOLVE_BODY, headers=admin("wrong")).status_code == 401
    assert prod.post("/resolve", json=RESOLVE_BODY, headers=admin(INGEST)).status_code == 401
    assert incidents.get_incident(inc)["resolver"] is None and isolated["retain"] == 0  # cannot pre-empt the resolver
    assert prod.post("/resolve", json=RESOLVE_BODY, headers=admin(ADMIN)).status_code == 200


def test_anonymous_feedback_cannot_change_ranking_inputs(prod):
    inc = make_live_incident()
    for _ in range(12):
        assert prod.post("/feedback", json=FEEDBACK_BODY).status_code in (401, 429)
    assert incidents.feedback_for(inc) == []


def test_protected_routes_leak_no_configured_secret(prod):
    make_live_incident()
    responses = [prod.post("/feedback", json=FEEDBACK_BODY), prod.post("/feedback", json=FEEDBACK_BODY, headers=admin(INGEST)),
                 prod.post("/resolve", json=RESOLVE_BODY), prod.post("/resolve", json=RESOLVE_BODY, headers=admin("wrong")),
                 prod.post("/feedback", json=FEEDBACK_BODY, headers=admin(ADMIN))]
    blob = " ".join(r.text + str(dict(r.headers)) for r in responses)
    assert ADMIN not in blob and INGEST not in blob


def test_duplicate_key_headers_are_rejected(prod):
    assert prod.post("/reset", headers=[("X-RecallOps-Key", ADMIN), ("X-RecallOps-Key", "second")]).status_code == 401
    assert prod.post("/reset", headers=[("X-RecallOps-Key", "wrong"), ("X-RecallOps-Key", ADMIN)]).status_code == 401
    assert prod.post("/reset", headers=[("X-RecallOps-Key", ADMIN)]).status_code == 200


# ---------------------------------------------------------------- CORS / SSE / docs / demo
def test_cors_headers_present_on_401_and_413(prod):
    origin = "http://localhost:5173"
    unauthorized = prod.post("/reset", headers={"Origin": origin})
    assert unauthorized.status_code == 401 and unauthorized.headers.get("access-control-allow-origin") == origin
    too_big = prod.post("/chat", content=b"x" * (LIMIT + 1), headers={"Origin": origin, "content-type": "application/json"})
    assert too_big.status_code == 413 and too_big.headers.get("access-control-allow-origin") == origin


def test_sse_response_is_streamed_not_buffered(isolated):
    async def scenario():
        release = asyncio.Event()
        sent = []

        async def sse_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/event-stream")]})
            await send({"type": "http.response.body", "body": b"event: token\ndata: 1\n\n", "more_body": True})
            await asyncio.wait_for(release.wait(), timeout=2)  # only proceeds once the client saw chunk 1
            await send({"type": "http.response.body", "body": b"event: done\ndata: {}\n\n", "more_body": False})

        async def send(message):
            sent.append(message)
            if message["type"] == "http.response.body" and message.get("more_body"):
                release.set()  # chunk 1 reached the client BEFORE the app finished

        async def receive():
            return {"type": "http.disconnect"}

        scope = {"type": "http", "method": "GET", "path": "/incidents/INC-1/briefing/stream", "headers": [], "client": ("1.2.3.4", 1)}
        await security.SecurityMiddleware(sse_app)(scope, receive, send)
        return sent

    assert [m["type"] for m in asyncio.run(scenario())] == ["http.response.start", "http.response.body", "http.response.body"]


def test_production_docs_disabled_and_dev_docs_unaffected(monkeypatch):
    import app.main as main

    monkeypatch.setenv("APP_ENV", "production")
    try:
        client = TestClient(importlib.reload(main).app)
        assert [client.get(p).status_code for p in ("/docs", "/redoc", "/openapi.json")] == [404, 404, 404]
    finally:
        monkeypatch.delenv("APP_ENV", raising=False)
        importlib.reload(main)
    assert TestClient(main.app).get("/docs").status_code == 200


def test_all_canonical_demo_alerts_usable_anonymously_and_custom_needs_key(prod):
    for index in range(len(DEMO)):
        security.reset_limiter()
        assert prod.post("/alert", json=demo_payload(index)).status_code == 200, DEMO[index]["alert_id"]
    security.reset_limiter()
    assert prod.post("/alert", json=demo_payload(0, title="custom")).status_code == 401
    assert prod.post("/alert", json=demo_payload(0, title="custom"), headers=admin(INGEST)).status_code == 200
