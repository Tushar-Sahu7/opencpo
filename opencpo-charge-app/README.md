# OCPP Charge App

A **PWA for EV drivers** — no app store required.

Scan a QR code on a charger, start charging, watch it live, get your receipt. Works on any phone browser. Built on FastAPI + Jinja2 + HTMX. No npm, no React, no build step.

---

## How It Works

```
Driver scans QR → Charger info → Start Charging → Live updates (SSE) → Stop → Receipt
```

1. Driver scans QR code on charger → `/charge/CP001/1`
2. Sees connector status, pricing, specs
3. Taps **Start Charging**
4. Live screen: power (kW), energy (kWh), SoC%, duration, cost
5. Taps **Stop** or unplugs → session summary + optional PDF receipt

---

## Architecture

The app is built around three separate concerns:

```
core/           Generic engine (API proxy, feature flags, JWT middleware)
routes/         Base page routes (home, charge, session, receipt, auth, QR, push)
plugins/        Optional modular features (account, favorites, receipts)
skins/          Branding layer (colors, logo, CSS)
templates/      Base Jinja2 templates
static/         Shared JS/assets (htmx, service worker, i18n, manifest)
```

### Skin System

Each skin lives in `skins/<name>/` and contains:

```
skins/my-brand/
  skin.json           Metadata (name, version, colors)
  static/
    style.css         Full mobile-first CSS — overrides all base styles
    logo.svg          Your brand logo (optional)
    favicon.svg       Your favicon (optional)
```

Set `SKIN=my-brand` in your `.env` to activate it.

Built-in skins are included under `skins/` — each demonstrates different branding approaches for your operators.  
The `skins/default/` folder is the generic built-in skin — clean, neutral, no branding.

### Plugin System

Plugins are FastAPI routers that auto-register. Enable them via `PLUGINS=account,receipts`.

Each plugin lives in `plugins/<name>/` and may include:
- `routes.py` — FastAPI router
- `templates/<name>/` — Jinja2 templates (searched after skin, before base)
- `__init__.py`

Template resolution order: **skin → plugins → base**

### Middleware

`core/middleware.py` runs on every request and injects into `request.state`:
- `flags` — feature flags (from Core API)
- `skin` — active skin name
- `account` — decoded JWT payload (or `None`)
- `lang` — detected language (nl/en)
- `t` — translation dict

---

## Quick Start

```bash
# 1. Clone and set up
git clone <repo>
cd ocpp-charge-app
cp .env.example .env
# Edit .env — set OCPP_CORE_API and JWT_SECRET at minimum

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run
python main.py
```

Open http://localhost:8003

### Using a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

---

## Configuration

All settings are environment variables. Copy `.env.example` to `.env`:

| Variable | Default | Description |
|---|---|---|
| `OCPP_CORE_API` | `http://localhost:8000` | URL of your OCPP Core API backend |
| `APP_TITLE` | `OCPP Charge` | App name shown in browser tab and headers |
| `APP_HOST` | `0.0.0.0` | Host to bind the server |
| `APP_PORT` | `8003` | Port to listen on |
| `JWT_SECRET` | `change-me-in-production` | Secret key for JWT auth cookies — **change this!** |
| `SKIN` | `default` | Skin folder name under `skins/` |
| `PLUGINS` | `receipts,account` | Comma-separated list of enabled plugins |

---

## Creating a Custom Skin

1. Copy the default skin as a starting point:
   ```bash
   cp -r skins/default skins/my-brand
   ```

2. Edit `skins/my-brand/skin.json`:
   ```json
   {
     "name": "My Brand",
     "version": "1.0",
     "colors": {
       "primary": "#ff6600",
       "background": "#1a1a2e"
     }
   }
   ```

3. Edit `skins/my-brand/static/style.css` — override CSS variables and styles.

4. Add your `logo.svg` and `favicon.svg` to `skins/my-brand/static/`.

5. Set `SKIN=my-brand` in `.env`.

The skin CSS is loaded **instead of** (not in addition to) the base static CSS — you have full control.

---

## Writing a Plugin

Create a folder under `plugins/`:

```
plugins/my-plugin/
  __init__.py
  routes.py        # FastAPI APIRouter
  templates/
    my-plugin/
      page.html
```

In `routes.py`:
```python
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/my-plugin/page", response_class=HTMLResponse)
async def my_page(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "my-plugin/page.html", {
        "flags": request.state.flags,
        "t": request.state.t,
        "account": request.state.account,
    })
```

Add `my-plugin` to `PLUGINS` in `.env`.

---

## Routes

```
GET  /                               Home / map
GET  /charge/{cp_id}/{connector}     QR landing — charger info + start button
POST /charge/{cp_id}/{connector}/start   Start charging session
GET  /session/{session_id}           Live charging screen (SSE)
POST /session/{session_id}/stop      Stop session
GET  /receipt/{session_id}           Session receipt
GET  /account/login                  Login page (account plugin)
GET  /account/register               Register page (account plugin)
GET  /account/profile                Profile (requires login)
GET  /account/history                Session history (requires login)
GET  /account/settings               Settings / language switcher
```

---

## Tech Stack

- [FastAPI](https://fastapi.tiangolo.com/) — web framework
- [Jinja2](https://jinja.palletsprojects.com/) — templating
- [HTMX](https://htmx.org/) — 14KB, handles SSE + forms (only JS dependency)
- [PyJWT](https://pyjwt.readthedocs.io/) — JWT auth cookies
- [Leaflet.js](https://leafletjs.com/) — map (CDN, optional)
- No npm, no build step, no React

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
