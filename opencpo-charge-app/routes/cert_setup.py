"""Certificate setup wizard — guided cert install for fleet drivers."""
import logging
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

import httpx
import config

logger = logging.getLogger(__name__)
router = APIRouter()

# Headers to forward from driver's browser to Core API (cert identity + OS detection)
_FORWARD_HEADERS = ("X-Client-Cert-Serial", "X-Client-Cert-DN", "X-Client-Cert-Verify", "User-Agent")

# Content types that should be returned as binary (not parsed as JSON)
_BINARY_TYPES = ("application/x-pkcs12", "application/x-pem-file", "application/x-x509-ca-cert")


# ── Wizard Page ───────────────────────────────────────────────────────────

@router.get("/setup/cert", response_class=HTMLResponse)
async def cert_setup_wizard(request: Request, token: str = ""):
    """
    Cert install wizard landing page.
    Driver arrives here from SMS/email link with ?token=...
    """
    templates = request.app.state.templates
    flags = getattr(request.state, "flags", {})
    t = getattr(request.state, "t", {})
    lang = getattr(request.state, "lang", "nl")

    driver_info = None
    error = None

    if not token:
        error = "missing_token"
    else:
        try:
            async with httpx.AsyncClient(base_url=config.CORE_API, timeout=5) as client:
                r = await client.get("/api/v1/public/cert-setup/validate", params={"token": token})
                if r.status_code == 200:
                    driver_info = r.json()
                elif r.status_code == 410:
                    detail = r.json().get("detail", "")
                    error = "token_used" if "already used" in detail else "token_expired"
                elif r.status_code == 404:
                    error = "token_invalid"
                else:
                    error = "token_error"
        except Exception:
            error = "token_error"

    return templates.TemplateResponse(request, "cert_setup.html", {
        "token": token,
        "driver": driver_info,
        "error": error,
        "flags": flags,
        "t": t,
        "lang": lang,
    })


# ── Generic Core API Proxy ────────────────────────────────────────────────
# All /api/cert-setup/* paths are forwarded to Core API at
# /api/v1/public/cert-setup/*. One proxy, no per-endpoint duplication.

@router.api_route("/api/cert-setup/{path:path}", methods=["GET", "POST"])
async def proxy_cert_setup(request: Request, path: str):
    """
    Proxy all cert-setup API calls to OCPP Core.

    Maps: /api/cert-setup/{path} → Core /api/v1/public/cert-setup/{path}
    Forwards: query params, request body, relevant headers.
    """
    core_url = f"/api/v1/public/cert-setup/{path}"
    fwd_headers = {h: request.headers[h] for h in _FORWARD_HEADERS if h in request.headers}

    async with httpx.AsyncClient(base_url=config.CORE_API, timeout=15) as client:
        if request.method == "POST":
            body = await request.body()
            r = await client.post(
                core_url,
                params=dict(request.query_params),
                content=body,
                headers={**fwd_headers, "Content-Type": request.headers.get("Content-Type", "application/json")},
            )
        else:
            r = await client.get(core_url, params=dict(request.query_params), headers=fwd_headers)

    # Binary responses (P12, PEM, certs) — return as-is
    content_type = r.headers.get("content-type", "")
    if any(bt in content_type for bt in _BINARY_TYPES):
        resp_headers = {}
        if "content-disposition" in r.headers:
            resp_headers["Content-Disposition"] = r.headers["content-disposition"]
        resp_headers["Cache-Control"] = "no-store, no-cache"
        return Response(content=r.content, media_type=content_type, headers=resp_headers)

    # JSON responses
    try:
        return JSONResponse(r.json(), status_code=r.status_code)
    except Exception:
        return Response(content=r.content, status_code=r.status_code, media_type=content_type)
