"""Home routes: map screen and nearby chargers API."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from core.api import api_get

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    templates = request.app.state.templates
    flags = getattr(request.state, "flags", {})
    return templates.TemplateResponse(request, "home.html", {
        "flags": flags,
        "t": getattr(request.state, "t", {}),
        "lang": getattr(request.state, "lang", "nl"),
    })


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "privacy.html", {
        "t": getattr(request.state, "t", {}),
        "lang": getattr(request.state, "lang", "nl"),
    })


@router.get("/api/chargers/nearby")
async def nearby_chargers(lat: float, lng: float, radius: float = 200):
    return await api_get(f"/api/v1/public/chargers/nearby?lat={lat}&lng={lng}&radius={radius}")
