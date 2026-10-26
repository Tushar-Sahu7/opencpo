"""
Favorites plugin — server-side sync for logged-in users.

The browser handles localStorage directly. These endpoints are bonus:
they sync to Core API when the user is logged in.

Routes:
  GET    /api/favorites           → list (from Core API if logged in)
  POST   /api/favorites/{cp_id}   → save (Core API + client handles localStorage)
  DELETE /api/favorites/{cp_id}   → unsave (Core API + client handles localStorage)
"""
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import config

logger = logging.getLogger(__name__)

router = APIRouter()

CORE_API = config.CORE_API
COOKIE_NAME = "auth_token"


def _get_token(request: Request) -> Optional[str]:
    """Get JWT from cookie, or None if not logged in."""
    return request.cookies.get(COOKIE_NAME)


async def _core_request(
    method: str,
    path: str,
    token: Optional[str] = None,
) -> tuple[int, dict]:
    """Proxy to Core API favorites endpoints."""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(base_url=CORE_API, timeout=8) as client:
            if method == "GET":
                r = await client.get(path, headers=headers)
            elif method == "POST":
                r = await client.post(path, headers=headers)
            elif method == "DELETE":
                r = await client.delete(path, headers=headers)
            else:
                return 400, {"error": "Ongeldige methode"}
        try:
            data = r.json()
        except Exception:
            data = {}
        return r.status_code, data
    except Exception as e:
        logger.warning(f"Core API favorites request failed: {e}")
        return 503, {"error": "Core API niet bereikbaar"}


# ── Routes ────────────────────────────────────────────────────────────────

@router.get("/api/favorites")
async def get_favorites(request: Request):
    """
    Return saved favorites from Core API if logged in.
    If not logged in, return empty list (browser uses localStorage).
    """
    token = _get_token(request)
    if not token:
        return JSONResponse({"favorites": [], "source": "localStorage"})

    status, data = await _core_request("GET", "/api/v1/public/account/favorites", token)
    if status == 200:
        return JSONResponse({**data, "source": "server"})
    if status == 401:
        return JSONResponse({"favorites": [], "source": "localStorage"})

    logger.warning(f"Favorites fetch failed: {status} {data}")
    return JSONResponse({"favorites": [], "source": "localStorage"})


@router.post("/api/favorites/{cp_id}")
async def save_favorite(cp_id: str, request: Request):
    """
    Save a charger to favorites.
    If logged in: also persists to Core API.
    localStorage save is handled by the browser JS.
    """
    token = _get_token(request)
    if not token:
        return JSONResponse({"ok": True, "synced": False})

    status, data = await _core_request(
        "POST", f"/api/v1/public/account/favorites/{cp_id}", token
    )
    if status in (200, 201):
        return JSONResponse({"ok": True, "synced": True, "cp_id": cp_id})
    if status == 401:
        return JSONResponse({"ok": True, "synced": False})

    logger.warning(f"Save favorite failed: {status} {data}")
    return JSONResponse({"ok": True, "synced": False})


@router.delete("/api/favorites/{cp_id}")
async def delete_favorite(cp_id: str, request: Request):
    """
    Remove a charger from favorites.
    If logged in: also removes from Core API.
    localStorage removal is handled by the browser JS.
    """
    token = _get_token(request)
    if not token:
        return JSONResponse({"ok": True, "synced": False})

    status, data = await _core_request(
        "DELETE", f"/api/v1/public/account/favorites/{cp_id}", token
    )
    if status == 200:
        return JSONResponse({"ok": True, "synced": True, "cp_id": cp_id})
    if status == 401:
        return JSONResponse({"ok": True, "synced": False})

    logger.warning(f"Delete favorite failed: {status} {data}")
    return JSONResponse({"ok": True, "synced": False})
