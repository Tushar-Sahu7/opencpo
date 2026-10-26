# Plugins

Plugins add optional feature modules to the charge app. Each plugin is a Python package with a FastAPI `APIRouter`. They're loaded at startup via auto-discovery — no changes to the engine needed.

---

## How Plugins Work

`plugins/__init__.py` contains `discover_plugins(names: list)`:

```python
def discover_plugins(names: list) -> list:
    routers = []
    for name in names:
        mod = importlib.import_module(f"plugins.{name}.routes")
        if hasattr(mod, "router"):
            routers.append(mod.router)
    return routers
```

`main.py` calls this with `config.PLUGINS` (a comma-separated list from the `PLUGINS` env var), and registers each returned router with the FastAPI app.

Template directories are also handled in `main.py` — it scans `plugins/{name}/templates/` and adds any that exist to Jinja2's search path.

---

## Creating a Plugin

### Step 1: Create the directory

```
plugins/myplugin/
├── __init__.py      # Can be empty
└── routes.py        # Must export `router`
```

### Step 2: `__init__.py`

Can be empty:
```python
# plugins/myplugin/__init__.py
```

### Step 3: `routes.py`

Must export a variable named `router` (a FastAPI `APIRouter`):

```python
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/myplugin/example", response_class=HTMLResponse)
async def example_page(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "myplugin/example.html", {
        "flags": getattr(request.state, "flags", {}),
        "t": getattr(request.state, "t", {}),
        "lang": getattr(request.state, "lang", "nl"),
    })
```

### Step 4: Add templates (optional)

```
plugins/myplugin/templates/myplugin/
└── example.html
```

The plugin subdirectory in `templates/` is important to avoid name collisions with other plugins and base templates.

### Step 5: Enable the plugin

In `.env`:
```
PLUGINS=receipts,account,myplugin
```

The plugin will be loaded automatically on the next startup.

---

## What's Available in Route Handlers

Every route handler has access to `request.state`, populated by `inject_context` middleware:

| `request.state.*` | Type | Description |
|---|---|---|
| `flags` | `dict` | Feature flags from Core API |
| `skin` | `str` | Active skin name |
| `account` | `dict \| None` | Decoded JWT payload, or `None` if not logged in |
| `lang` | `str` | Active language (`"nl"` or `"en"`) |
| `t` | `dict` | Translation strings for the active language |

Access them defensively (middleware runs before routes, but be safe):
```python
flags = getattr(request.state, "flags", {})
account = getattr(request.state, "account", None)
t = getattr(request.state, "t", {})
lang = getattr(request.state, "lang", "nl")
```

The templates object is at `request.app.state.templates`.

---

## Complete Example: Maintenance Mode Plugin

This plugin shows a maintenance banner on any page and provides an API endpoint to toggle it.

```
plugins/maintenance/
├── __init__.py
├── routes.py
└── templates/maintenance/
    └── banner.html
```

**`__init__.py`:**
```python
# Empty
```

**`routes.py`:**
```python
"""
Maintenance mode plugin.

Adds:
  GET  /maintenance/status  → JSON: {"active": bool, "message": str}
  POST /maintenance/toggle  → Toggle maintenance mode on/off
  GET  /maintenance/banner  → HTMX partial: maintenance banner (if active)

Usage in templates:
  {% if flags.maintenance_mode %}
    <div hx-get="/maintenance/banner" hx-trigger="load"></div>
  {% endif %}
"""
import logging
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory state (replace with Redis/DB for multi-process deployments)
_maintenance_state = {
    "active": False,
    "message": "We are performing scheduled maintenance. Back shortly.",
}


@router.get("/maintenance/status")
async def maintenance_status():
    """Return current maintenance mode state."""
    return JSONResponse(_maintenance_state)


@router.post("/maintenance/toggle")
async def maintenance_toggle(request: Request):
    """Toggle maintenance mode. Requires admin JWT (check account role)."""
    account = getattr(request.state, "account", None)
    if not account or account.get("role") != "admin":
        return JSONResponse({"error": "Unauthorized"}, status_code=403)

    _maintenance_state["active"] = not _maintenance_state["active"]
    logger.info(f"Maintenance mode: {_maintenance_state['active']}")
    return JSONResponse({"ok": True, **_maintenance_state})


@router.post("/maintenance/message")
async def set_maintenance_message(request: Request):
    """Update the maintenance message text."""
    account = getattr(request.state, "account", None)
    if not account or account.get("role") != "admin":
        return JSONResponse({"error": "Unauthorized"}, status_code=403)

    body = await request.json()
    _maintenance_state["message"] = body.get("message", _maintenance_state["message"])
    return JSONResponse({"ok": True})


@router.get("/maintenance/banner", response_class=HTMLResponse)
async def maintenance_banner(request: Request):
    """
    HTMX partial: returns a maintenance banner if active, empty otherwise.
    Templates use hx-get="/maintenance/banner" hx-trigger="load".
    """
    if not _maintenance_state["active"]:
        return HTMLResponse("")  # Empty = no banner

    templates = request.app.state.templates
    return templates.TemplateResponse(request, "maintenance/banner.html", {
        "message": _maintenance_state["message"],
    })
```

**`templates/maintenance/banner.html`:**
```html
<div style="
  background: rgba(234, 179, 8, 0.12);
  border: 1px solid rgba(234, 179, 8, 0.3);
  border-radius: 10px;
  padding: 12px 16px;
  color: #eab308;
  font-size: 14px;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
">
  <span>⚠️</span>
  <span>{{ message }}</span>
</div>
```

**Enable it:**
```
PLUGINS=receipts,account,maintenance
```

**Use it in a base template:**
```html
<!-- Inside any page template, poll for banner every 60s -->
<div hx-get="/maintenance/banner"
     hx-trigger="load, every 60s"
     hx-swap="outerHTML">
</div>
```

---

## Built-in Plugins

The repo ships three plugins:

### `account`
Login, registration, profile, and session history for EV drivers. Auth via OTP (phone number). JWT stored in `auth_token` HttpOnly cookie.

Routes: `GET/POST /account/login`, `GET/POST /account/register`, `GET /account/profile`, `GET /account/history`, `POST /account/settings`

### `receipts`
Re-exports the core `receipt` router. Enabled by default. Keeping it as a plugin means it can be disabled for deployments that don't want receipts (e.g. fleet-only).

### `favorites`
Sync charger favorites between browser localStorage and Core API. Only syncs when the driver is logged in; falls back to localStorage-only for guests.

Routes: `GET/POST/DELETE /api/favorites`, `POST/DELETE /api/favorites/{cp_id}`

---

## Plugin Conventions

- **One router per plugin** — `routes.py` exports `router`.
- **No database** — plugins are stateless thin proxies. Persistent state belongs in Core API.
- **Template namespace** — always use `plugins/templates/myplugin/file.html` paths to avoid conflicts.
- **Graceful degradation** — if Core API is unavailable, return empty data (not 500s).
- **Auth check pattern** — check `request.state.account` for authenticated endpoints; redirect to `/account/login` if `None`.
