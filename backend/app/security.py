"""Minimal production hardening (hackathon grade). One place for every security decision.

Hardened mode is on when APP_ENV=production OR any of ADMIN_API_KEY / INGEST_API_KEY is set.
Off (local dev / the offline test-suite) everything behaves exactly as before, apart from the
always-on request-size cap and nosniff header.

When hardened:
  * POST /seed, POST /reset  -> require ADMIN_API_KEY in the X-RecallOps-Key header. Fail closed:
    in production with no key configured they are simply unusable.
  * POST /alert -> require INGEST_API_KEY (or ADMIN_API_KEY) OR content that EXACTLY matches one of
    the predefined server-side demo alerts (backend/data/demo_alerts.json). A match is replaced by
    the canonical server copy, so callers cannot inject text through the public demo path.
    Custom alert text without a key is rejected.
  * POST /feedback, POST /resolve -> also require ADMIN_API_KEY (an ingest-only key is NOT enough):
    anonymous feedback could flip rankings and anonymous resolves write LLM-processed text into memory.
    On top of the key they stay narrowed: live incidents only, known fix types, per-incident cap,
    resolve-once (see check_feedback_allowed/check_resolve_allowed). The operator sets the key in the
    browser at runtime (sessionStorage 'recallops_key'); it is never bundled.
  * Request bodies: the ACTUAL received bytes are counted against MAX_BODY_BYTES (Content-Length is
    only an early hint), so a false or missing Content-Length cannot bypass the cap.
  * Per-IP and global in-process rate limits (HTTP 429) on the expensive routes.

No secret is ever logged or returned. Keys are compared in constant time. CORS is NOT authentication
and is not treated as such anywhere here.
"""
from __future__ import annotations

import hmac
import json
import logging
import re
import time
from collections import deque
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app import config

logger = logging.getLogger("recallops.security")

KEY_HEADER = b"x-recallops-key"
MAX_BODY_BYTES = 64 * 1024
MAX_FEEDBACK_PER_INCIDENT = 12
DEMO_ALERTS_PATH = Path(__file__).resolve().parent.parent / "data" / "demo_alerts.json"


def hardened() -> bool:
    return config.is_production() or bool(config.admin_api_key() or config.ingest_api_key())


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": {"code": code, "message": message}})


# --- credentials ------------------------------------------------------------------------
def _key_matches(presented: str | None, *expected: str) -> bool:
    """Constant-time comparison; never short-circuits on which key matched."""
    if not presented:
        return False
    ok = False
    for candidate in expected:
        if candidate and hmac.compare_digest(presented.encode("utf-8"), candidate.encode("utf-8")):
            ok = True
    return ok


def is_admin(presented: str | None) -> bool:
    return _key_matches(presented, config.admin_api_key())


def is_ingest(presented: str | None) -> bool:
    return _key_matches(presented, config.ingest_api_key(), config.admin_api_key())


# --- rate limiting (per process; sliding window) ------------------------------------------
class _Limiter:
    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = {}

    def allow(self, key: tuple[str, str], limit: int, window: float = 60.0) -> bool:
        now = time.monotonic()
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - window:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        if len(self._hits) > 5000:  # bound memory: drop idle keys
            for k in [k for k, v in self._hits.items() if not v or v[-1] <= now - window]:
                self._hits.pop(k, None)
        return True

    def reset(self) -> None:
        self._hits.clear()


_limiter = _Limiter()


def reset_limiter() -> None:
    _limiter.reset()


# (method, path regex, bucket name, per-IP per-minute, global per-minute). Conservative for one judge.
_RULES: list[tuple[str, re.Pattern[str], str, int, int]] = [
    ("POST", re.compile(r"^/(seed|reset)$"), "admin", 5, 10),
    ("POST", re.compile(r"^/alert$"), "alert", 10, 60),
    ("POST", re.compile(r"^/chat$"), "chat", 20, 120),
    ("POST", re.compile(r"^/compare$"), "compare", 10, 60),
    ("POST", re.compile(r"^/feedback$"), "feedback", 30, 120),
    ("POST", re.compile(r"^/resolve$"), "resolve", 6, 30),
    ("GET", re.compile(r"^/incidents/[^/]+/briefing/stream$"), "briefing", 20, 120),
]
_READ_RULE = ("read", 240, 2000)  # every other GET (health, dashboards): generous


def _rule_for(method: str, path: str) -> tuple[str, int, int] | None:
    for m, rx, name, per_ip, global_limit in _RULES:
        if method == m and rx.match(path):
            return name, per_ip, global_limit
    return _READ_RULE if method == "GET" else None


_ADMIN_POST_PATHS = ("/seed", "/reset", "/feedback", "/resolve")


def _client_ip(scope: dict[str, Any], headers: dict[bytes, bytes]) -> str:
    hops = config.trusted_proxy_hops()
    if hops > 0:
        parts = [p.strip() for p in headers.get(b"x-forwarded-for", b"").decode("latin-1").split(",") if p.strip()]
        if len(parts) >= hops:
            return parts[-hops]
    client = scope.get("client")
    return client[0] if client else "unknown"


# --- ASGI middleware ------------------------------------------------------------------------
async def _buffer_body(receive) -> tuple[list[dict[str, Any]], bool]:
    """Read http.request frames until the body ends, counting ACTUAL bytes. Stops as soon as the
    cumulative size exceeds MAX_BODY_BYTES, so at most limit+one frame is ever held in memory.
    Returns (frames, exceeded)."""
    frames: list[dict[str, Any]] = []
    total = 0
    while True:
        message = await receive()
        frames.append(message)
        if message["type"] != "http.request":  # e.g. http.disconnect: hand it to the app as-is
            return frames, False
        total += len(message.get("body", b""))
        if total > MAX_BODY_BYTES:
            return frames, True
        if not message.get("more_body", False):
            return frames, False


def _replay(frames: list[dict[str, Any]], receive):
    pending = list(frames)

    async def replay() -> dict[str, Any]:
        if pending:
            return pending.pop(0)
        return await receive()

    return replay


async def _respond(send, status: int, code: str, message: str, extra: list[tuple[bytes, bytes]] | None = None) -> None:
    body = json.dumps({"detail": {"error": {"code": code, "message": message}}}).encode()
    await send({
        "type": "http.response.start", "status": status,
        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                    (b"x-content-type-options", b"nosniff"), *(extra or [])],
    })
    await send({"type": "http.response.body", "body": body})


class SecurityMiddleware:
    """Pure ASGI (does not buffer, so the SSE briefing stream is unaffected)."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method, path = scope["method"], scope["path"]
        headers = {k.lower(): v for k, v in scope.get("headers", [])}

        # Always on: bound request bodies by what is ACTUALLY received. Content-Length is only an
        # early rejection hint; a false or missing one cannot bypass the cap.
        if method in ("POST", "PUT", "PATCH"):
            length = headers.get(b"content-length")
            if length is not None:
                try:
                    too_big = int(length) > MAX_BODY_BYTES
                except ValueError:
                    too_big = True
                if too_big:
                    await _respond(send, 413, "payload_too_large", "request body too large")
                    return
            frames, exceeded = await _buffer_body(receive)
            if exceeded:
                await _respond(send, 413, "payload_too_large", "request body too large")
                return
            receive = _replay(frames, receive)

        if hardened() and method != "OPTIONS":
            # Ambiguous credentials: several X-RecallOps-Key headers are rejected outright.
            if sum(1 for k, _ in scope.get("headers", []) if k.lower() == KEY_HEADER) > 1:
                await _respond(send, 401, "unauthorized", "unauthorized")
                return
            rule = _rule_for(method, path)
            if rule is not None:
                name, per_ip, global_limit = rule
                ip = _client_ip(scope, headers)
                if not (_limiter.allow((name, ip), per_ip) and _limiter.allow((name, "*"), global_limit)):
                    logger.warning("rate limit exceeded bucket=%s", name)
                    await _respond(send, 429, "rate_limited", "too many requests", [(b"retry-after", b"60")])
                    return
            if method == "POST" and path in _ADMIN_POST_PATHS:
                presented = headers.get(KEY_HEADER, b"").decode("latin-1")
                if not is_admin(presented):
                    logger.warning("unauthorized admin request path=%s", path)
                    await _respond(send, 401, "unauthorized", "unauthorized")
                    return

        async def send_with_headers(message) -> None:
            if message["type"] == "http.response.start":
                message = dict(message)
                message["headers"] = [*message.get("headers", []), (b"x-content-type-options", b"nosniff")]
            await send(message)

        await self.app(scope, receive, send_with_headers)


# --- /alert: ingest key OR exact predefined demo alert --------------------------------------
def _norm(value: Any) -> str:
    return (value or "").strip() if isinstance(value, str) or value is None else str(value)


def _demo_fingerprint(d: dict[str, Any]) -> tuple[str, ...]:
    return tuple(_norm(d.get(k)) for k in ("service", "severity", "title", "symptoms", "error_message", "log_snippet", "error_signature"))


def _match_demo_alert(alert) -> dict[str, Any] | None:
    fingerprint = _demo_fingerprint(alert.model_dump())
    for demo in json.loads(DEMO_ALERTS_PATH.read_text(encoding="utf-8")):
        if _demo_fingerprint(demo) == fingerprint:
            return demo
    return None


def authorize_alert(alert, presented_key: str | None):
    """Returns the Alert to process. Un-hardened: unchanged. Hardened + valid key: unchanged.
    Hardened + no/invalid key: only an exact predefined demo alert is accepted, and the server's
    canonical copy (not the caller's) is what gets processed."""
    if not hardened():
        return alert
    if is_ingest(presented_key):
        return alert
    demo = _match_demo_alert(alert)
    if demo is None:
        raise _error(401, "unauthorized", "Custom alerts require authorization. Use one of the predefined demo alerts unchanged.")
    from app import incidents
    from app.models import Alert

    if len(incidents.live_incidents()) >= config.max_live_incidents():
        raise _error(429, "capacity", "live incident capacity reached; try again later")
    return Alert(  # canonical server-side content; client-supplied alert_id/deploy/metrics/submitted_at are dropped
        service=demo["service"], severity=demo["severity"], title=demo["title"], symptoms=demo.get("symptoms"),
        error_message=demo["error_message"], log_snippet=demo["log_snippet"], error_signature=demo.get("error_signature"),
    )


# --- /feedback and /resolve narrowing (public because the browser calls them) -------------------
def check_feedback_allowed(incident_id: str, fix_type: str) -> None:
    if not hardened():
        return
    from app import incidents, memory

    if memory.get_seed_incident(incident_id) is not None:
        raise _error(403, "forbidden", "feedback is only accepted for live incidents")
    incident = incidents.get_incident(incident_id) or {}
    known = {f.get("fix_type") for f in (incident.get("ranked_fixes") or [])}
    if fix_type not in known:
        raise _error(422, "invalid_fix_type", "fix_type is not one of this incident's recommended fixes")
    if len(incidents.feedback_for(incident_id)) >= MAX_FEEDBACK_PER_INCIDENT:
        raise _error(429, "feedback_limit", "feedback limit reached for this incident")


def check_resolve_allowed(incident_id: str) -> None:
    if not hardened():
        return
    from app import incidents, memory

    if memory.get_seed_incident(incident_id) is not None:
        raise _error(403, "forbidden", "only live incidents can be resolved")
    if (incidents.get_incident(incident_id) or {}).get("resolver"):
        raise _error(409, "already_resolved", "incident already resolved")


def startup_warnings() -> None:
    """Names only, never values."""
    if config.is_production():
        if not config.admin_api_key():
            logger.warning("APP_ENV=production but ADMIN_API_KEY is not set: /seed and /reset are disabled (fail closed)")
        if not config.ingest_api_key():
            logger.warning("INGEST_API_KEY is not set: only predefined demo alerts can be ingested")
    elif config.admin_api_key() or config.ingest_api_key():
        logger.warning("API keys configured while APP_ENV is not production: hardened mode is on")
