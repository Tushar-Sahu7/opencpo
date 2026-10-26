"""Charge screen: charger info, connector status, rate, start button."""
import logging
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from core.api import api_get

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/charge/{cp_id}/{connector}", response_class=HTMLResponse)
async def charge_screen(request: Request, cp_id: str, connector: str):
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

    site_id = request.query_params.get("site_id", "")
    evse_id = request.query_params.get("evse_id", "")
    qr_code = request.query_params.get("qr_code", "")
    display_name = site_id if site_id else cp_id.capitalize()

    charger_data = None
    charger_error = None
    try:
        charger_data = await api_get(f"/api/v1/chargers/{cp_id}")
    except Exception as e:
        charger_error = str(e)

    conn_status = "Available"
    if charger_data:
        # Check live connector status first (real-time from OCPP heartbeat)
        live = charger_data.get("live", {})
        live_status_key = f"connector_{connector}_status"
        live_status = live.get(live_status_key) if live else None
        if live_status:
            conn_status = live_status
        else:
            # Fall back to connectors array from charger config
            for c in charger_data.get("connectors", []):
                if c.get("connector_id") == connector or c.get("id") == connector:
                    conn_status = c.get("status", "Available")
                    break

    rate_value = None
    rate_label = "Fixed rate"
    preauth_amount = "€25"
    tariff_kwh_raw = 0.0
    charger_power_kw = 0.0
    address = ""
    lat = None
    lng = None
    pricing_tier = "public"

    # Determine driver's pricing tier from cert/JWT identity
    account = getattr(request.state, "account", None)
    if account:
        pricing_tier = account.get("pricing_tier", "public")

    # Fetch dynamic tier pricing (independent of charger availability)
    try:
        pricing = await api_get("/api/v1/pricing/current")
        tier_data = pricing.get("tiers", {}).get(pricing_tier, {})
        tier_rate = tier_data.get("rate_incl")
        if tier_rate:
            tariff_kwh_raw = float(tier_rate)
            rate_value = f"€ {tariff_kwh_raw:.4f}/kWh".replace(".", ",")
            tier_name = tier_data.get("name", pricing_tier)
            rate_label = f"{tier_name} rate" if pricing_tier != "public" else "Rate"
    except Exception:
        pass

    if charger_data:
        # Fallback: charger's flat tariff if dynamic pricing unavailable
        if rate_value is None:
            tariff = charger_data.get("tariff_kwh")
            if tariff:
                tariff_kwh_raw = float(tariff)
                rate_value = f"€ {tariff_kwh_raw:.4f}/kWh".replace(".", ",")

        power = charger_data.get("max_power_kw") or charger_data.get("power_kw") or 0
        charger_power_kw = float(power)
        address = charger_data.get("address") or charger_data.get("location") or ""
        lat = charger_data.get("lat") or charger_data.get("latitude")
        lng = charger_data.get("lng") or charger_data.get("longitude")
        if not display_name or display_name == cp_id.capitalize():
            display_name = charger_data.get("name") or charger_data.get("site_name") or display_name

    return templates.TemplateResponse(request, "charge.html", {
        "cp_id": cp_id,
        "connector": connector,
        "display_name": display_name,
        "evse_id": evse_id,
        "qr_code": qr_code,
        "site_id": site_id,
        "conn_status": conn_status,
        "rate_value": rate_value,
        "rate_label": rate_label,
        "preauth_amount": preauth_amount,
        "charger_error": charger_error,
        "tariff_kwh_raw": tariff_kwh_raw,
        "charger_power_kw": charger_power_kw,
        "address": address,
        "lat": lat,
        "lng": lng,
        "flags": flags,
        "t": getattr(request.state, "t", {}),
        "lang": getattr(request.state, "lang", "nl"),
    })
