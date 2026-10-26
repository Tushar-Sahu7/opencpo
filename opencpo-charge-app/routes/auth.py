"""Auth routes: OTP flow for driver identification."""
import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi import HTTPException

from core.api import api_post

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/auth/{cp_id}/{connector}", response_class=HTMLResponse)
async def auth_screen(request: Request, cp_id: str, connector: str):
    try:
        connector = int(connector)
    except (ValueError, TypeError):
        logger.error(f"Invalid connector '{connector}' for {cp_id} — refusing to default")
        templates = request.app.state.templates
        flags = getattr(request.state, "flags", {})
        return templates.TemplateResponse(request, "error.html", {
            "message": "Invalid connector",
            "detail": "The connector could not be determined. Please scan the QR code again.",
            "flags": flags,
            "t": getattr(request.state, "t", {}),
            "lang": getattr(request.state, "lang", "nl"),
        }, status_code=400)
    templates = request.app.state.templates
    flags = getattr(request.state, "flags", {})
    return templates.TemplateResponse(request, "auth.html", {
        "cp_id": cp_id,
        "connector": connector,
        "flags": flags,
        "t": getattr(request.state, "t", {}),
        "lang": getattr(request.state, "lang", "nl"),
    })


@router.post("/api/auth/send-otp")
async def send_otp(request: Request):
    body = await request.json()
    try:
        result = await api_post("/api/v1/public/auth/send-otp", {"phone": body.get("phone")})
        return JSONResponse(result)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)


@router.post("/api/auth/verify-otp")
async def verify_otp(request: Request):
    body = await request.json()
    try:
        result = await api_post("/api/v1/public/auth/verify-otp", {
            "phone": body.get("phone"),
            "code": body.get("code"),
        })
        return JSONResponse(result)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
