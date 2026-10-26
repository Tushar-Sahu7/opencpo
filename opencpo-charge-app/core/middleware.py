"""Middleware: injects feature flags, skin name, account state, and language into request.state."""
import json
import logging
import os
from datetime import datetime, timezone
import config
from core.flags import get_flags

import httpx
import jwt

logger = logging.getLogger(__name__)

JWT_SECRET = config.JWT_SECRET
JWT_ALGO = "HS256"
COOKIE_NAME = "auth_token"
DEVICE_COOKIE = "device_auth"
DEVICE_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days

SUPPORTED_LANGS = {"nl", "en"}
DEFAULT_LANG = os.environ.get("DEFAULT_LANG", "en")

# Load translations once at import time
_I18N_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "i18n.json")
try:
    with open(_I18N_PATH, encoding="utf-8") as _f:
        _TRANSLATIONS: dict = json.load(_f)
except Exception:
    _TRANSLATIONS = {"nl": {}, "en": {}}


def _detect_lang(request) -> str:
    """Detect language: cookie → query param → default nl.

    Default is always Dutch. Language only changes when the user explicitly
    selects English via the switcher (?lang=en) or a persisted cookie.
    Accept-Language header is intentionally ignored — Dutch-first policy.
    """
    # 1. Cookie (persisted explicit choice)
    cookie_lang = request.cookies.get("lang")
    if cookie_lang in SUPPORTED_LANGS:
        return cookie_lang

    # 2. Query param (explicit switcher click)
    query_lang = request.query_params.get("lang")
    if query_lang in SUPPORTED_LANGS:
        return query_lang

    return DEFAULT_LANG


async def _resolve_cert_identity(serial: str) -> dict | None:
    """Call Core API to resolve cert serial → driver account. Returns None on any failure."""
    try:
        async with httpx.AsyncClient(base_url=config.CORE_API, timeout=3) as client:
            r = await client.get("/api/v1/public/cert/identify", params={"serial": serial})
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.debug(f"Cert identity lookup failed: {e}")
    return None


async def inject_context(request, call_next):
    """Inject flags, skin, account, language, and translations into request.state."""
    request.state.flags = await get_flags()
    request.state.skin = config.SKIN
    request.state.auth_method = None

    # ── 1. Client certificate (strongest — Safari with mTLS) ────────────
    cert_serial = (request.headers.get("X-Client-Cert-Serial") or "").strip()
    request.state.account = None
    _set_device_cookie = False

    if cert_serial:
        account = await _resolve_cert_identity(cert_serial)
        if account:
            request.state.account = account
            request.state.auth_method = "cert"
            _set_device_cookie = True  # Refresh device cookie on every cert hit

    # ── 2. Device auth cookie (PWA fallback — signed JWT from cert) ───────
    if request.state.account is None:
        device_token = request.cookies.get(DEVICE_COOKIE)
        if device_token:
            try:
                payload = jwt.decode(device_token, JWT_SECRET, algorithms=[JWT_ALGO])
                request.state.account = payload
                request.state.auth_method = "device_cookie"
            except jwt.ExpiredSignatureError:
                pass  # Expired — will fall through to OTP or anonymous
            except Exception:
                pass

    # ── 3. OTP session JWT (existing flow) ────────────────────────────────
    if request.state.account is None:
        token = request.cookies.get(COOKIE_NAME)
        if token:
            try:
                payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
                request.state.account = payload
                request.state.auth_method = "jwt"
            except Exception:
                pass

    # ── 4. Cert renewal check ────────────────────────────────────────────
    request.state.cert_renewal_needed = False
    request.state.cert_days_left = None
    if request.state.auth_method == "cert" and request.state.account:
        cert_expires = request.state.account.get("cert_expires_at")
        if cert_expires:
            try:
                exp = datetime.fromisoformat(cert_expires)
                days_left = (exp - datetime.now(timezone.utc)).days
                request.state.cert_days_left = days_left
                if days_left < 30:
                    request.state.cert_renewal_needed = True
            except Exception:
                pass

    # Language detection and translation injection
    lang = _detect_lang(request)
    request.state.lang = lang
    request.state.t = _TRANSLATIONS.get(lang, _TRANSLATIONS.get(DEFAULT_LANG, {}))

    # ── 5. Inject account into Jinja2 template context ──────────────────
    # So base.html nav can always check `account` without each route passing it
    templates = getattr(request.app.state, "templates", None)
    if templates:
        templates.env.globals["account"] = request.state.account
        templates.env.globals["auth_method"] = request.state.auth_method
        templates.env.globals["cert_renewal_needed"] = request.state.cert_renewal_needed
        templates.env.globals["cert_days_left"] = request.state.cert_days_left

    response = await call_next(request)

    # Set device_auth cookie when cert identifies successfully
    if _set_device_cookie and request.state.account:
        acct = request.state.account
        device_jwt = jwt.encode({
            "id": acct.get("id", ""),
            "email": acct.get("email", ""),
            "name": acct.get("name", ""),
            "pricing_tier": acct.get("pricing_tier", "public"),
            "group_id": acct.get("group_id"),
            "cert_serial": acct.get("cert_serial", ""),
        }, JWT_SECRET, algorithm=JWT_ALGO)
        response.set_cookie(
            DEVICE_COOKIE, device_jwt,
            max_age=DEVICE_COOKIE_MAX_AGE,
            httponly=True, secure=True, samesite="lax",
        )

    # Set lang cookie if query param was used (persist the choice)
    query_lang = request.query_params.get("lang")
    if query_lang in SUPPORTED_LANGS:
        response.set_cookie("lang", query_lang, max_age=60 * 60 * 24 * 30, samesite="lax")

    return response
