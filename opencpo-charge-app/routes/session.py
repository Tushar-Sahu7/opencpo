"""Session routes: create, live view, poll, stop, cancel."""
import logging

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from core.api import api_get, api_post

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/sessions/create")
async def create_session(request: Request):
    body = await request.json()
    # Map phone → driver_phone if needed (auth form sends "phone")
    if "phone" in body and "driver_phone" not in body:
        body["driver_phone"] = body.pop("phone")

    cp_id = body.get("cp_id")
    connector_id = body.get("connector_id")
    driver_phone = body.get("driver_phone")

    # Deduplication: check for existing pending/unconfirmed session for this
    # phone+charger+connector to avoid creating duplicate sessions on redirect loops.
    if driver_phone and cp_id:
        try:
            existing = await api_get(
                f"/api/v1/public/sessions/pending?cp_id={cp_id}&driver_phone={driver_phone}"
            )
            # If a pending session exists for the SAME connector, reuse it
            if existing and isinstance(existing, dict):
                ex_connector = existing.get("connector_id")
                ex_status = existing.get("status", "")
                if ex_connector == connector_id and ex_status in ("pending", "awaiting_payment"):
                    return JSONResponse(existing)
        except Exception:
            # Endpoint may not exist or return 404 — not fatal, proceed to create
            pass

    # Check connector status via OCPP Core API before creating session.
    # If connector is Charging/Occupied, reject with a user-friendly error
    # instead of taking payment for a session that will be rejected by the charger.
    if cp_id and connector_id:
        try:
            charger_data = await api_get(f"/api/v1/chargers/{cp_id}")
            occupied_statuses = {"Charging", "SuspendedEV", "SuspendedEVSE", "Finishing", "Occupied"}
            conn_status = None

            # Check live status first (real-time from OCPP heartbeat)
            live = charger_data.get("live", {})
            if live:
                live_key = f"connector_{connector_id}_status"
                conn_status = live.get(live_key)

            # Fall back to connectors array
            if not conn_status:
                for conn in charger_data.get("connectors", []):
                    cid = conn.get("connector_id") or conn.get("id")
                    if cid == connector_id:
                        conn_status = conn.get("status")
                        break

            if conn_status and conn_status in occupied_statuses:
                logger.warning(
                    f"Session creation blocked: {cp_id} connector {connector_id} is {conn_status}"
                )
                return JSONResponse(
                    {"error": "Connector busy — this connector is already in use."},
                    status_code=409,
                )
        except Exception as e:
            # Non-fatal: if we can't check status, proceed and let Core API decide
            logger.warning(f"Could not check connector status for {cp_id}/{connector_id}: {e}")

    try:
        result = await api_post("/api/v1/public/sessions", body)
        return JSONResponse(result)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)


@router.get("/session/{session_id}", response_class=HTMLResponse)
async def live_session(request: Request, session_id: str):
    templates = request.app.state.templates
    flags = getattr(request.state, "flags", {})
    return templates.TemplateResponse(request, "session.html", {
        "session_id": session_id,
        "flags": flags,
        "t": getattr(request.state, "t", {}),
        "lang": getattr(request.state, "lang", "nl"),
    })


@router.get("/api/sessions/{session_id}/poll")
async def poll_session(session_id: str):
    try:
        data = await api_get(f"/api/v1/public/sessions/{session_id}")
        return JSONResponse(data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/sessions/{session_id}/stop")
async def stop_session(session_id: str):
    try:
        result = await api_post(f"/api/v1/public/sessions/{session_id}/stop", {})
        return JSONResponse(result)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)


@router.post("/api/sessions/{session_id}/cancel")
async def cancel_session(session_id: str):
    try:
        result = await api_post(f"/api/v1/public/sessions/{session_id}/cancel", {})
        return JSONResponse(result)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
