"""
Account plugin routes — login, register, profile, history.
The charge app is a thin proxy: all logic lives in Core API.
JWT stored in HttpOnly cookie 'auth_token'.
"""
import logging
import os
from typing import Optional

import httpx
import jwt
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

import config

logger = logging.getLogger(__name__)

router = APIRouter()

CORE_API = config.CORE_API
JWT_SECRET = config.JWT_SECRET
JWT_ALGO = "HS256"
COOKIE_NAME = "auth_token"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def _get_account_from_request(request: Request) -> Optional[dict]:
    """Decode JWT from cookie — returns payload or None."""
    return getattr(request.state, "account", None)


def _require_login(request: Request):
    """Return RedirectResponse to login if not logged in, else None."""
    if not _get_account_from_request(request):
        return RedirectResponse("/account/login", status_code=302)
    return None


async def _proxy_to_core(
    method: str,
    path: str,
    body: Optional[dict] = None,
    token: Optional[str] = None,
) -> tuple[int, dict]:
    """Proxy a request to Core API, returning (status_code, json_body)."""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(base_url=CORE_API, timeout=10) as client:
        if method == "GET":
            r = await client.get(path, headers=headers)
        elif method == "PUT":
            r = await client.put(path, json=body, headers=headers)
        else:
            r = await client.post(path, json=body or {}, headers=headers)

    try:
        data = r.json()
    except Exception:
        data = {"detail": "Server error"}

    return r.status_code, data


# ── Page routes ───────────────────────────────────────────────────────────

@router.get("/account/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    templates = request.app.state.templates
    flags = getattr(request.state, "flags", {})
    t = getattr(request.state, "t", {})
    lang = getattr(request.state, "lang", "nl")
    account = _get_account_from_request(request)
    return templates.TemplateResponse(request, "account/settings.html", {
        "flags": flags, "t": t, "lang": lang,
        "account": account,
    })


@router.get("/account/login", response_class=HTMLResponse)
async def login_page(request: Request):
    templates = request.app.state.templates
    # Already logged in → redirect to profile
    if _get_account_from_request(request):
        return RedirectResponse("/account/profile", status_code=302)
    flags = getattr(request.state, "flags", {})
    t = getattr(request.state, "t", {})
    lang = getattr(request.state, "lang", "nl")
    return templates.TemplateResponse(request, "account/login.html", {
        "flags": flags, "t": t, "lang": lang,
        "account": None,
        "error": None,
    })


@router.get("/account/register", response_class=HTMLResponse)
async def register_page(request: Request):
    templates = request.app.state.templates
    if _get_account_from_request(request):
        return RedirectResponse("/account/profile", status_code=302)
    flags = getattr(request.state, "flags", {})
    t = getattr(request.state, "t", {})
    lang = getattr(request.state, "lang", "nl")
    return templates.TemplateResponse(request, "account/register.html", {
        "flags": flags, "t": t, "lang": lang,
        "account": None,
        "error": None,
    })


@router.get("/account/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    templates = request.app.state.templates
    redirect = _require_login(request)
    if redirect:
        return redirect
    account = _get_account_from_request(request)
    auth_method = getattr(request.state, "auth_method", None)
    flags = getattr(request.state, "flags", {})
    t = getattr(request.state, "t", {})
    lang = getattr(request.state, "lang", "nl")

    if auth_method == "cert":
        # Cert-authenticated: account data already resolved by middleware
        data = {
            "email": account.get("email", ""),
            "name": account.get("name", ""),
            "phone": account.get("phone", ""),
            "language": account.get("language", "nl"),
            "pricing_tier": account.get("pricing_tier", "public"),
            "auth_method": "cert",
        }
    else:
        # JWT-authenticated: fetch fresh profile from Core API
        token = request.cookies.get(COOKIE_NAME)
        status, data = await _proxy_to_core("GET", "/api/v1/public/account/profile", token=token)
        if status != 200:
            resp = RedirectResponse("/account/login", status_code=302)
            resp.delete_cookie(COOKIE_NAME)
            return resp

    return templates.TemplateResponse(request, "account/profile.html", {
        "flags": flags, "t": t, "lang": lang,
        "account": account,
        "profile": data,
        "error": None,
    })


@router.get("/account/history", response_class=HTMLResponse)
async def history_page(request: Request):
    templates = request.app.state.templates
    redirect = _require_login(request)
    if redirect:
        return redirect
    account = _get_account_from_request(request)
    token = request.cookies.get(COOKIE_NAME)
    flags = getattr(request.state, "flags", {})
    t = getattr(request.state, "t", {})
    lang = getattr(request.state, "lang", "nl")

    status, data = await _proxy_to_core("GET", "/api/v1/public/account/sessions", token=token)
    if status != 200:
        data = {"sessions": [], "total": 0, "total_kwh": 0, "total_cost": 0}

    return templates.TemplateResponse(request, "account/history.html", {
        "flags": flags, "t": t, "lang": lang,
        "account": account,
        "sessions": data.get("sessions", []),
        "total_sessions": data.get("total", 0),
        "total_kwh": data.get("total_kwh", 0),
        "total_cost": data.get("total_cost", 0),
    })


# ── API proxy routes ──────────────────────────────────────────────────────

@router.post("/api/account/login")
async def api_login(request: Request):
    body = await request.json()
    status, data = await _proxy_to_core("POST", "/api/v1/public/account/login", body=body)

    if status != 200:
        return JSONResponse({"error": data.get("detail", "Login failed")}, status_code=status)

    token = data.get("token")
    resp = JSONResponse({"ok": True, "account": data.get("account")})
    if token:
        resp.set_cookie(
            key=COOKIE_NAME,
            value=token,
            httponly=True,
            secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
            samesite="lax",
            max_age=COOKIE_MAX_AGE,
            path="/",
        )
    return resp


@router.post("/api/account/register")
async def api_register(request: Request):
    body = await request.json()
    status, data = await _proxy_to_core("POST", "/api/v1/public/account/register", body=body)

    if status != 200:
        return JSONResponse({"error": data.get("detail", "Registration failed")}, status_code=status)

    token = data.get("token")
    resp = JSONResponse({"ok": True, "account": data.get("account")})
    if token:
        resp.set_cookie(
            key=COOKIE_NAME,
            value=token,
            httponly=True,
            secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
            samesite="lax",
            max_age=COOKIE_MAX_AGE,
            path="/",
        )
    return resp


@router.post("/api/account/logout")
async def api_logout(request: Request):
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


@router.get("/api/account/sessions")
async def api_sessions(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    status, data = await _proxy_to_core("GET", "/api/v1/public/account/sessions", token=token)
    if status != 200:
        return JSONResponse({"error": data.get("detail", "Error")}, status_code=status)
    return JSONResponse(data)


@router.put("/api/account/profile")
async def api_update_profile(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    body = await request.json()
    status, data = await _proxy_to_core("PUT", "/api/v1/public/account/profile", body=body, token=token)
    if status != 200:
        return JSONResponse({"error": data.get("detail", "Error saving profile")}, status_code=status)
    return JSONResponse({"ok": True, "profile": data})
