"""Thin HTTP proxy to the OCPP Core API."""
import logging
import os

import httpx
from fastapi import HTTPException

import config

logger = logging.getLogger(__name__)

CORE_API_KEY = os.getenv("MANAGEMENT_API_KEY", "")


def _auth_headers() -> dict:
    """Return X-API-Key header for management API calls if key is configured."""
    return {"X-API-Key": CORE_API_KEY} if CORE_API_KEY else {}


async def api_get(path: str) -> dict:
    """GET request to Core API. Raises HTTPException on failure."""
    async with httpx.AsyncClient(base_url=config.CORE_API, timeout=10, headers=_auth_headers()) as client:
        r = await client.get(path)
        r.raise_for_status()
        return r.json()


async def api_post(path: str, body: dict) -> dict:
    """POST request to Core API. Raises HTTPException with API error detail."""
    async with httpx.AsyncClient(base_url=config.CORE_API, timeout=10, headers=_auth_headers()) as client:
        r = await client.post(path, json=body)
        if not r.is_success:
            try:
                err = r.json()
                detail = err.get("detail", f"API error {r.status_code}")
            except Exception:
                detail = f"API error {r.status_code}"
            raise HTTPException(status_code=r.status_code, detail=detail)
        return r.json()
