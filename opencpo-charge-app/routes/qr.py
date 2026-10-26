"""QR sticker landing: lookup charger from code and redirect."""
import logging
from urllib.parse import quote

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from core.api import api_get

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/c/{code}", response_class=HTMLResponse)
async def qr_landing(request: Request, code: str):
    """QR sticker → lookup charger → redirect to charge screen."""
    templates = request.app.state.templates
    flags = getattr(request.state, "flags", {})
    try:
        data = await api_get(f"/api/v1/public/qr/{quote(code, safe='')}/lookup")
        cp_id = data["cp_id"]
        connector_id = data["connector_id"]
        site_id = data.get("site_id", "")
        evse_id = data.get("evse_id", "")
        redirect_url = f"/charge/{cp_id}/{connector_id}"
        if site_id or evse_id:
            redirect_url += f"?site_id={quote(str(site_id))}&evse_id={quote(str(evse_id))}&qr_code={quote(code)}"
        else:
            redirect_url += f"?qr_code={quote(code)}"
        return RedirectResponse(redirect_url, status_code=302)
    except HTTPException as e:
        return templates.TemplateResponse(request, "error.html", {
            "message": "QR-code niet gevonden",
            "detail": "This QR code is not active or not linked to a charger.",
            "code": code,
            "flags": flags,
            "t": getattr(request.state, "t", {}),
            "lang": getattr(request.state, "lang", "nl"),
        }, status_code=404)
    except Exception as e:
        logger.error(f"QR lookup error: {e}")
        return templates.TemplateResponse(request, "error.html", {
            "message": "Error looking up charger",
            "detail": str(e),
            "code": code,
            "flags": flags,
            "t": getattr(request.state, "t", {}),
            "lang": getattr(request.state, "lang", "nl"),
        }, status_code=500)
