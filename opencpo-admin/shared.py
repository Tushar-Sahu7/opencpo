"""Shared helpers for CPO Admin route modules.

All route modules import from here — never from main.py.
"""
import os
import json
import time
import copy
import logging
from contextvars import ContextVar
from datetime import datetime, timezone

import httpx
from fastapi import Request
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

# OCPP Core API (internal — used by server-side Python code)
CORE_API = os.getenv("OCPP_CORE_API_URL", os.getenv("OCPP_CORE_API", "http://localhost:8000"))
CORE_API_KEY = os.getenv("CORE_API_KEY", "")
APP_TITLE = os.getenv("APP_TITLE", "OpenCPO Admin")

# PKI data directory (shared volume with ocpp-core)
PKI_DATA_DIR = os.getenv("PKI_DATA_DIR", "/app/data/pki")

# Public URLs — used by the frontend (top nav, JS, docs links).
# These MUST be configurable: never hardcode production domains.
# Default to localhost for local installs; set env vars for production/public deployments.
CHARGE_APP_URL = os.getenv("CHARGE_APP_URL", "http://localhost:8003")
CHARGER_FARM_URL = os.getenv("CHARGER_FARM_URL", "http://localhost:8087")
COMPLIANCE_URL = os.getenv("COMPLIANCE_URL", "http://localhost:8090")
CORE_API_PUBLIC_URL = os.getenv("CORE_API_PUBLIC_URL", "http://localhost:8000")

# Templates (shared instance)
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
templates.env.globals["app_title"] = APP_TITLE
templates.env.globals["charge_app_url"] = CHARGE_APP_URL
templates.env.globals["charger_farm_url"] = CHARGER_FARM_URL
templates.env.globals["compliance_url"] = COMPLIANCE_URL
templates.env.globals["core_api_public_url"] = CORE_API_PUBLIC_URL


def format_datetime(val, default: str = "—") -> str:
    """Format any date/time (datetime object, timestamp, ISO string) into a clean, readable 'YYYY-MM-DD HH:MM:SS' string."""
    if not val:
        return default
    if isinstance(val, (int, float)):
        try:
            val = datetime.fromtimestamp(val, tz=timezone.utc)
        except Exception:
            return str(val)
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d %H:%M:%S")
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d %H:%M:%S")

    s = str(val).strip()
    if not s or s.lower() in ("none", "null", "-", "—"):
        return default
    if s in ("Never", "Just now", "stale"):
        return s

    # If it is already just a date: YYYY-MM-DD
    if len(s) == 10 and s.count("-") == 2:
        return s

    # Parse ISO / standard datetime string
    try:
        clean = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    # Fallback cleanup for ISO-like strings: replace 'T', trim microseconds and offsets
    if "T" in s or len(s) >= 19:
        s_clean = s.replace("T", " ")
        if len(s_clean) >= 19 and s_clean[4] == "-" and s_clean[7] == "-":
            return s_clean[:19]

    return s


def format_date(val, default: str = "—") -> str:
    """Format any date/time into a clean 'YYYY-MM-DD' string."""
    if not val:
        return default
    s = format_datetime(val, default=default)
    if s == default or s in ("Never", "Just now", "stale"):
        return s
    if len(s) >= 10 and s.count("-") >= 2:
        return s[:10]
    return s


def format_time(val, default: str = "—") -> str:
    """Format any date/time into a clean 'HH:MM:SS' string."""
    if not val:
        return default
    s = format_datetime(val, default=default)
    if s == default or s in ("Never", "Just now", "stale"):
        return s
    if len(s) >= 19 and " " in s:
        return s[11:19]
    return s


templates.env.filters["format_datetime"] = format_datetime
templates.env.filters["readable_time"] = format_datetime
templates.env.filters["format_date"] = format_date
templates.env.filters["format_time"] = format_time

# ── Per-Request User Context (SEC-01: prevents cross-session identity bleed) ─
current_user_ctx: ContextVar[dict | None] = ContextVar("current_user_ctx", default=None)


def get_current_user() -> dict:
    """Return an isolated cloned copy of the user bound to the current async request context."""
    u = current_user_ctx.get()
    return copy.deepcopy(u) if u else {}

# ── Local JWT verification (avoids calling core /me on every request) ─────
_JWT_SECRET = os.getenv("JWT_SECRET", os.getenv("CORE_API_KEY", ""))
_JWT_ALGO = "HS256"


def _verify_token_local(token: str) -> dict | None:
    """Decode and verify a JWT locally. Returns payload dict or None."""
    try:
        import jwt as pyjwt
        payload = pyjwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGO])
        # Check expiry manually (pyjwt raises on expiry, but belt-and-suspenders)
        exp = payload.get("exp", 0)
        if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
            logger.warning("verify_session: token expired")
            return None
        return payload
    except Exception as exc:
        logger.warning("verify_session: local JWT verify failed: %s", exc)
        return None


_setup_cache = {"complete": None, "timestamp": 0.0}
_client_pool: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """Return a shared singleton httpx.AsyncClient with keepalive connection pooling."""
    global _client_pool
    if _client_pool is None or _client_pool.is_closed:
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=50, keepalive_expiry=30.0)
        timeout = httpx.Timeout(10.0, connect=3.0)
        _client_pool = httpx.AsyncClient(base_url=CORE_API, limits=limits, timeout=timeout)
    return _client_pool


async def close_http_client() -> None:
    """Close the shared HTTP client pool on app shutdown."""
    global _client_pool
    if _client_pool is not None and not _client_pool.is_closed:
        try:
            await _client_pool.aclose()
        except Exception:
            pass
        _client_pool = None


async def get_setup_status() -> dict:
    """Check if the platform has been configured (first-time setup). Cached in memory."""
    global _setup_cache
    now = time.time()
    # Cache positive setup complete for 5 minutes
    if _setup_cache["complete"] is True and (now - _setup_cache["timestamp"]) < 300:
        return {"complete": True, "steps": {}}

    try:
        client = get_http_client()
        r = await client.get("/api/v1/admin/setup/status")
        if r.status_code == 200:
            data = r.json()
            if data.get("complete"):
                _setup_cache = {"complete": True, "timestamp": now}
            return data
        # If core returns 429 or transient error, keep existing cached state rather than kicking user out
        if _setup_cache["complete"] is True:
            return {"complete": True, "steps": {}}
    except Exception:
        if _setup_cache["complete"] is True:
            return {"complete": True, "steps": {}}

    return {"complete": False, "steps": {}}


def get_session_token(request: Request) -> str | None:
    """Extract JWT from the session cookie."""
    return request.cookies.get("opencpo_session")


async def verify_session(request: Request) -> dict | None:
    """Verify the JWT session cookie locally (no core API call).
    
    Decodes and validates the JWT expiry right here. Falls back to calling
    core /me only if local verification fails (e.g. different secret key).
    Returns a user dict or None.
    """
    token = get_session_token(request)
    if not token:
        logger.warning("verify_session: no opencpo_session cookie found")
        return None

    # Try local JWT verification first — avoids rate limiting core auth
    payload = _verify_token_local(token)
    if payload:
        return {
            "id": int(payload.get("sub", 0)),
            "email": payload.get("email", ""),
            "name": payload.get("name", payload.get("email", "")),
            "role": payload.get("role", "admin"),
        }

    # Fallback: call core /me (different secret, key rotation, etc.)
    logger.info("verify_session: local verify failed, falling back to core /me")
    try:
        client = get_http_client()
        r = await client.get(
            "/api/v1/admin/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        if r.status_code == 200:
            return r.json()
        logger.warning("verify_session: core /me returned %s", r.status_code)
    except Exception as exc:
        logger.warning("verify_session: exception calling core /me: %s", exc)
    return None


async def api(path: str, method: str = "GET", json: dict = None,
              token: str = None) -> dict | httpx.Response:
    """Call OCPP Core API. Returns parsed JSON response.
    Sends CORE_API_KEY as X-API-Key header if available.
    Reuses persistent httpx connection pool.
    """
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if CORE_API_KEY:
        headers["X-API-Key"] = CORE_API_KEY

    client = get_http_client()
    url = f"/api/v1{path}"
    r = await client.request(method, url, json=json, headers=headers)
    r.raise_for_status()
    return r.json()
