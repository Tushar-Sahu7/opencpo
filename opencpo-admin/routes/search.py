"""Global search route — search assets, chargers, sessions, tariffs, and navigation."""
import logging
from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse

from shared import api

logger = logging.getLogger(__name__)
router = APIRouter()

# Static quick-jump pages
_PAGES = [
    {"name": "Dashboard", "category": "Navigation", "keywords": "dashboard fleet home overview", "url": "/"},
    {"name": "Chargers", "category": "Navigation", "keywords": "chargers fleet evse hardware connectors assets", "url": "/chargers"},
    {"name": "Sessions", "category": "Navigation", "keywords": "sessions transactions charging history logs energy", "url": "/sessions"},
    {"name": "Receipts & Billing", "category": "Navigation", "keywords": "receipts billing invoices revenue costs vat", "url": "/receipts"},
    {"name": "Tariffs & Pricing", "category": "Navigation", "keywords": "tariffs pricing rates cost energy rate fee", "url": "/tariffs"},
    {"name": "Tokens & RFID", "category": "Navigation", "keywords": "tokens rfid cards tags auth whitelist drivers", "url": "/tokens"},
    {"name": "OCPI Roaming", "category": "Navigation", "keywords": "ocpi roaming partners emsp cpo cdr credentials", "url": "/ocpi"},
    {"name": "OCPP Live Stream", "category": "Navigation", "keywords": "ocpp live websocket messages logs stream", "url": "/ocpp"},
    {"name": "Network & Tailscale", "category": "Navigation", "keywords": "network tailscale vpn wireguard connectivity", "url": "/network"},
    {"name": "Settings", "category": "Navigation", "keywords": "settings config credentials branding api keys backup", "url": "/settings"},
    {"name": "Documentation", "category": "Navigation", "keywords": "docs documentation help api guide subsidies", "url": "/docs"},
]


@router.get("/api/search")
async def global_search(q: str = Query("", description="Search term")):
    query = q.strip().lower()
    if not query:
        return JSONResponse({"query": "", "results": [], "count": 0})

    results = []

    # 1. Match Navigation Pages
    for p in _PAGES:
        if query in p["name"].lower() or query in p["keywords"]:
            results.append({
                "category": "Pages",
                "title": p["name"],
                "subtitle": f"Go to {p['name']}",
                "url": p["url"],
                "badge": "Page",
                "icon": "compass"
            })

    # 2. Match Chargers / Assets
    try:
        charger_data = await api("/chargers?limit=100")
        chargers = charger_data.get("chargers", [])
        for c in chargers:
            cid = c.get("id", "")
            vendor = c.get("vendor", "") or ""
            model = c.get("model", "") or ""
            site = c.get("site", "") or ""
            status = c.get("status", "offline")

            if (query in cid.lower() or 
                query in vendor.lower() or 
                query in model.lower() or 
                query in site.lower()):
                
                details = f"{vendor} {model}".strip()
                if site:
                    details = f"{details} · {site}" if details else site

                results.append({
                    "category": "Chargers",
                    "title": cid,
                    "subtitle": details or "Charge Point",
                    "url": f"/chargers",
                    "badge": status.upper(),
                    "badge_color": "green" if status == "online" else "slate",
                    "icon": "zap"
                })
                if len(results) >= 20:
                    break
    except Exception as e:
        logger.warning("Search: failed to query chargers: %s", e)

    # 3. Match Charging Sessions
    try:
        session_data = await api("/sessions?limit=50")
        sessions = session_data.get("sessions", [])
        for s in sessions:
            cp = s.get("charge_point", "")
            auth_id = s.get("auth_id", "") or ""
            txn = str(s.get("transaction_id") or "")
            status = s.get("status", "")
            energy = s.get("energy_kwh", 0) or 0

            if (query in cp.lower() or 
                query in auth_id.lower() or 
                query == txn):
                
                results.append({
                    "category": "Sessions",
                    "title": f"Session on {cp}",
                    "subtitle": f"Txn #{txn} · Auth: {auth_id} · {energy:.1f} kWh",
                    "url": f"/sessions",
                    "badge": status.upper(),
                    "badge_color": "emerald" if status == "active" else "blue",
                    "icon": "activity"
                })
                if len(results) >= 25:
                    break
    except Exception as e:
        logger.warning("Search: failed to query sessions: %s", e)

    # 4. Match Tariffs
    try:
        tariff_data = await api("/tariffs")
        tariffs = tariff_data.get("tariffs", [])
        for t in tariffs:
            tname = t.get("name", "")
            tid = t.get("id", "")
            rate = t.get("energy_rate", 0)

            if query in tname.lower() or query in tid.lower():
                results.append({
                    "category": "Tariffs",
                    "title": tname,
                    "subtitle": f"Rate: €{rate:.4f}/kWh",
                    "url": "/tariffs",
                    "badge": "Tariff",
                    "badge_color": "purple",
                    "icon": "coins"
                })
    except Exception as e:
        logger.warning("Search: failed to query tariffs: %s", e)

    return JSONResponse({
        "query": q,
        "results": results[:20],  # Cap to top 20 relevant results
        "count": len(results)
    })

