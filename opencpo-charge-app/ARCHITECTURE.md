# Charge App — Architecture Spec
**Date:** March 27, 2026
**Authors:** Ignacio + Clio
**Principle:** Spec first, build second. Same approach as the platform rebuild.

---

## 1. What This Is

A web-based progressive web app (PWA) for EV drivers to find chargers, start sessions, pay, and monitor charging. Runs in any browser, installable on any phone.

**Two layers:**
- **Engine** — agnostic, open-sourceable. Routes, API proxy, plugin loader, feature flags, service worker.
- **Skin** — branding, CSS, custom templates. Operators can create their own skins.

The engine is skin-agnostic. The skin applies operator-specific branding.

---

## 2. Directory Structure

```
opencpo-charge-app/
├── main.py                    App entry — route registration, plugin loader
├── config.py                  Env-based config (CORE_API, SKIN, PLUGINS)
├── core/                      Engine (open-source)
│   ├── api.py                 Thin proxy to OCPP Core API
│   ├── flags.py               Feature flag reader (cached from Core API)
│   └── middleware.py          Flag injection, skin resolution
├── routes/                    Base routes (one file per flow)
│   ├── home.py                Map + charger discovery
│   ├── charge.py              Charger detail + connector picker
│   ├── auth.py                OTP / account login
│   ├── session.py             Live session + stop
│   └── receipt.py             Receipt screen + PDF download
├── plugins/                   Feature modules (each self-contained)
│   ├── __init__.py            Plugin auto-discovery
│   ├── history/               Charging history
│   │   ├── routes.py          GET /history
│   │   └── templates/         history.html
│   ├── account/               Optional login/registration
│   │   ├── routes.py          GET /account, POST /account/login
│   │   └── templates/         login.html, profile.html
│   ├── receipts/              PDF receipt generation
│   │   └── generator.py       reportlab/weasyprint PDF builder
│   ├── estimator/             Cost estimator
│   │   └── routes.py          GET /api/estimate
│   ├── favorites/             Saved chargers (localStorage + optional sync)
│   │   └── routes.py
│   ├── push/                  Push notifications (service worker)
│   │   └── sw.js
│   ├── co2/                   CO₂ savings calculator
│   │   └── routes.py
│   └── pwa/                   PWA manifest + install prompt
│       ├── manifest.json
│       └── sw.js
├── templates/                 Base templates (engine default)
│   ├── base.html              Shell — loads skin CSS, injects flags
│   ├── home.html              Map screen
│   ├── charge.html            Charger detail
│   ├── auth.html              Auth screen
│   ├── session.html           Live session (renamed from live.html)
│   ├── receipt.html           Receipt screen
│   └── error.html             Error page
├── static/                    Base static assets
│   ├── app.js                 Core JS (shared utilities)
│   ├── home.js                Map + discovery JS
│   └── session.js             Live session JS
├── skins/                     Skin overrides
│   └── default/               Built-in default skin
│       ├── skin.json          Metadata: name, colors, fonts
│       ├── static/
│       │   └── style.css      Full CSS override
│       └── templates/         Template overrides (optional)
└── ROADMAP.md                 Feature roadmap + decisions
```

---

## 3. Plugin System

### Loading
```python
# config.py
PLUGINS = os.getenv("PLUGINS", "receipts,pwa").split(",")
SKIN = os.getenv("SKIN", "default")
```

```python
# plugins/__init__.py
def discover_plugins(plugin_names: list[str]) -> list[APIRouter]:
    """Import and return routers from enabled plugins."""
    routers = []
    for name in plugin_names:
        try:
            mod = importlib.import_module(f"plugins.{name}.routes")
            if hasattr(mod, "router"):
                routers.append(mod.router)
        except ImportError:
            pass
    return routers
```

### Plugin Contract
Each plugin is a directory with:
- `routes.py` — FastAPI APIRouter (optional, for routes)
- `templates/` — Jinja2 templates (optional, for pages)
- `static/` — JS/CSS (optional)

A plugin can also be JS-only (no routes) — loaded via feature flag in templates:
```html
{% if flags.cost_estimator %}
  <script src="/static/plugins/estimator.js"></script>
{% endif %}
```

### Plugin Independence
- Plugins don't import each other
- Plugins only talk to Core API (via the same `api.py` proxy)
- Plugins can define their own templates or extend base templates
- A plugin with routes registers under its own prefix: `/history/`, `/account/`, etc.

---

## 4. Skin System

### Resolution Order
Templates: `skins/{SKIN}/templates/` → `templates/` (fallback)
Static: `skins/{SKIN}/static/` → `static/` (fallback)

```python
# In main.py
skin_dir = f"skins/{SKIN}"
template_dirs = []
if os.path.isdir(f"{skin_dir}/templates"):
    template_dirs.append(f"{skin_dir}/templates")
template_dirs.append("templates")  # base fallback
templates = Jinja2Templates(directory=template_dirs)
```

### skin.json
```json
{
  "name": "Stroomlijnen",
  "version": "1.0",
  "colors": {
    "primary": "#00B0E4",
    "secondary": "#84BD00",
    "background": "#0a1628"
  },
  "logo": "/static/logo.svg",
  "favicon": "/static/favicon.svg"
}
```

### What This Means
- Open-source users: clean functional UX (base templates + base CSS)
- Stroomlijnen: example branded skin (dark theme, animations, custom branding)
- Other CPOs: their own skin, same engine + same plugins

---

## 5. Feature Flags

### Storage
PostgreSQL table `ocpp.feature_flags` in Core API.

### Flow
1. Core API exposes `GET /api/v1/features` → `{"map": true, "history": false, ...}`
2. Charge app fetches on startup, caches 60s
3. Flags injected into every template render: `{{ flags }}`
4. JS gets flags via: `window.FEATURES = {{ flags | tojson }};`
5. Admin panel toggles via `POST /api/v1/features/{key}/toggle`

### Rules
- Flags are **global** (same for all chargers, all users)
- Flags control **visibility**, not logic. The code is always there; the flag shows/hides it.
- A disabled flag means the feature's routes still exist but templates don't render the UI
- PDF receipts are **not** behind a flag — they're mandatory

---

## 6. User Identity

### Three Tiers
1. **Anonymous** — OTP per session, phone as soft ID
2. **Phone-linked** — no account, but phone number links sessions (history by phone)
3. **Account** — email + password, full profile (behind `account_login` flag)

### Retroactive Linking
When a user creates an account with a phone number, all previous sessions on that phone number are linked to the account.

### Storage
- Anonymous sessions: `ocpp.public_sessions.driver_phone`
- Accounts: `ocpp.driver_accounts` table (id, email, phone, password_hash, name, created_at)
- Session linking: `ocpp.public_sessions.driver_account_id` (nullable FK)

---

## 7. Data Flow

```
Driver's Browser
    ↓ HTTPS
Charge App (FastAPI, port 8003)        ← thin proxy + template renderer
    ↓ HTTP (internal)
OCPP Core API (port 8000)              ← all logic, all data
    ↓
PostgreSQL + Redis + Event Bus
    ↓
Charger (OCPP WebSocket)
```

The charge app NEVER:
- Touches the database directly
- Sends OCPP commands directly
- Stores session state (stateless proxy)

The charge app ONLY:
- Proxies API calls to Core API
- Renders templates with data from Core API
- Reads feature flags from Core API
- Serves static assets (skin CSS/JS)

---

## 8. API Surface

All charge app routes proxy to Core API `/api/v1/public/*`:

| Charge App Route | Core API Endpoint | Purpose |
|---|---|---|
| `GET /` | — | Home (map, static) |
| `GET /api/chargers/nearby` | `GET /api/v1/public/chargers/nearby` | Charger discovery |
| `GET /c/{code}` | `GET /api/v1/public/qr/{code}/lookup` | QR sticker landing |
| `GET /charge/{cp}/{conn}` | `GET /api/v1/chargers/{cp}` | Charger detail |
| `POST /api/auth/send-otp` | `POST /api/v1/public/auth/send-otp` | Send OTP |
| `POST /api/auth/verify-otp` | `POST /api/v1/public/auth/verify-otp` | Verify OTP |
| `POST /api/sessions/create` | `POST /api/v1/public/sessions` | Create session |
| `GET /api/sessions/{id}/poll` | `GET /api/v1/public/sessions/{id}` | Poll live data |
| `POST /api/sessions/{id}/stop` | `POST /api/v1/public/sessions/{id}/stop` | Stop session |
| `POST /api/sessions/{id}/cancel` | `POST /api/v1/public/sessions/{id}/cancel` | Cancel unpaid |
| `GET /api/sessions/{id}/pdf` | `GET /api/v1/public/sessions/{id}/pdf` | Download receipt |
| `GET /api/features` | `GET /api/v1/features` | Feature flags |

Plugin routes add their own prefixes:
- `/history/` — charging history (plugin)
- `/account/` — login/register (plugin)
- `/api/estimate` — cost estimator (plugin)

---

## 9. No File Over 500 Lines

This is a hard constraint from the architecture doc. Enforcement:
- `main.py` — app setup + plugin/skin loading only (~50 lines)
- Routes split by flow (home, charge, auth, session, receipt)
- JS extracted to static files
- CSS in skin directory
- Each plugin is self-contained

---

## 10. Build Plan

### Step 0: Restructure
Refactor current flat `main.py` into the directory structure above. Move existing routes to `routes/`. Move current CSS to `skins/default/static/`. No new features — just restructure.

### Step 1: Feature Flag System
- Core API: `ocpp.feature_flags` table + API endpoints
- Admin: Feature toggle panel
- Charge app: flag reader + template injection

### Step 2: PDF Receipts (mandatory)
- Plugin: `plugins/receipts/generator.py`
- VAT-compliant PDF with session data, tariff, operator company details
- Core API endpoint for PDF generation
- Auto-generate on session completion

### Step 3: PWA
- Plugin: `plugins/pwa/`
- manifest.json, service worker, install prompt
- Offline: cached session screen works without connection

### Step 4: Account System
- Plugin: `plugins/account/`
- Registration, login, profile
- Retroactive phone → account linking

### Step 5: Charging History
- Plugin: `plugins/history/`
- Phone-based first (no account needed)
- Account-based when account plugin is enabled

### Steps 6+: Features per ROADMAP.md priority

---

*This spec is the contract. Code follows the spec. If the spec is wrong, fix the spec first.*
