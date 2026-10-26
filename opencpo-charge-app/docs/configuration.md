# Configuration

All configuration is through environment variables. There is no config file — everything is read from the environment (or a `.env` file via `python-dotenv`).

Copy `.env.example` to `.env` and fill in your values:
```bash
cp .env.example .env
```

---

## Environment Variables

### `OCPP_CORE_API`
**Default:** `http://localhost:8000`

The base URL of the OCPP Core API backend. All API calls (`api_get`, `api_post`) are proxied to this URL.

```
OCPP_CORE_API=https://api.example.com
```

The charge app is a thin frontend — all business logic (sessions, auth, charger data, receipts, PDFs) lives in this API.

---

### `APP_TITLE`
**Default:** `OCPP Charge`

Display name shown in the browser tab and app headers.

```
APP_TITLE=My Charging Network
```

This value is injected into every Jinja2 template via `templates.env.globals["app_title"]`.

---

### `JWT_SECRET`
**Default:** `change-me-in-production`

Secret key used to decode JWT tokens from the `auth_token` HttpOnly cookie. The Core API issues the tokens; this app only decodes them to read the payload (account info, role).

```
JWT_SECRET=a-long-random-string-here
```

⚠️ **Must match the JWT secret used by Core API.** Use a strong random value in production — at least 32 characters.

---

### `SKIN`
**Default:** `default`

Which skin to activate. Must match a directory name under `skins/`.

```
SKIN=mycompany
```

The `default` skin is a neutral dark theme with no branding. See [skins.md](./skins.md) for how to create a custom skin.

---

### `APP_HOST`
**Default:** `0.0.0.0`

Host address for the uvicorn server to bind to. Use `0.0.0.0` to accept connections on all interfaces, or `127.0.0.1` to restrict to localhost (e.g. behind nginx).

```
APP_HOST=127.0.0.1
```

---

### `APP_PORT`
**Default:** `8003`

TCP port for the uvicorn server.

```
APP_PORT=8080
```

---

### `PLUGINS`
**Default:** `receipts,account`

Comma-separated list of plugins to enable. Plugin names must match directory names under `plugins/`.

```
PLUGINS=receipts,account,favorites,maintenance
```

Plugins are loaded in the order listed. Unknown plugin names log a warning but don't cause a startup failure.

Available built-in plugins:
- `receipts` — receipt screen and PDF download
- `account` — login, register, profile, session history
- `favorites` — charger favorites with server sync

See [plugins.md](./plugins.md) for how to write custom plugins.

---

## Summary Table

| Variable | Default | Required | Description |
|---|---|---|---|
| `OCPP_CORE_API` | `http://localhost:8000` | Yes (in production) | Backend API base URL |
| `APP_TITLE` | `OCPP Charge` | No | App display name |
| `JWT_SECRET` | `change-me-in-production` | **Yes** | JWT decode secret (must match Core API) |
| `SKIN` | `default` | No | Active skin name |
| `APP_HOST` | `0.0.0.0` | No | Bind host |
| `APP_PORT` | `8003` | No | Bind port |
| `PLUGINS` | `receipts,account` | No | Enabled plugins (comma-separated) |

---

## Example `.env` for Production

```dotenv
OCPP_CORE_API=https://api.my-charging-network.com
APP_TITLE=My Charging Network
JWT_SECRET=s3cr3t-very-long-random-string-here
SKIN=mycompany
APP_HOST=127.0.0.1
APP_PORT=8003
PLUGINS=receipts,account,favorites
```

---

## Running the App

```bash
# Development (with auto-reload)
python main.py

# Or with uvicorn directly
uvicorn main:app --host 0.0.0.0 --port 8003 --reload

# Production
uvicorn main:app --host 127.0.0.1 --port 8003 --workers 2
```

Behind nginx, proxy to `127.0.0.1:8003` and terminate TLS at nginx.
