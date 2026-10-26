# User Flows

This document describes the main user journeys through the charge app, with sequence diagrams for each.

---

## 1. QR Scan → Charge → Receipt

The primary flow. An EV driver scans a QR sticker on a charger, starts a charging session, monitors it live, stops it, and downloads a receipt.

```mermaid
sequenceDiagram
    actor Driver
    participant App as Charge App
    participant Core as Core API

    Driver->>App: Scan QR sticker → GET /c/{code}
    App->>Core: GET /api/v1/public/qr/{code}/lookup
    Core-->>App: {cp_id, connector_id, site_id, evse_id}
    App-->>Driver: 302 Redirect → /charge/{cp_id}/{connector_id}

    Driver->>App: GET /charge/{cp_id}/{connector}
    App->>Core: GET /api/v1/chargers/{cp_id}
    Core-->>App: {name, connectors, tariff_kwh, status, address}
    App-->>Driver: Charge screen (name, status badge, rate, Start button)

    Driver->>App: Tap "Start Charging" → POST /api/sessions/create
    Note over App: Body: {cp_id, connector_id, driver_phone or JWT}
    App->>Core: POST /api/v1/public/sessions
    Core-->>App: {session_id, status: "Pending"}
    App-->>Driver: 302 Redirect → /session/{session_id}

    Driver->>App: GET /session/{session_id}
    App-->>Driver: Live session page (power display, stats)

    loop Every 3 seconds
        Driver->>App: GET /api/sessions/{session_id}/poll
        App->>Core: GET /api/v1/public/sessions/{session_id}
        Core-->>App: {status, kwh, duration, cost, power_kw}
        App-->>Driver: Live stats update (htmx / JS)
    end

    Driver->>App: Tap "Stop" → POST /api/sessions/{session_id}/stop
    App->>Core: POST /api/v1/public/sessions/{session_id}/stop
    Core-->>App: {status: "Completed", kwh, cost}
    App-->>Driver: 302 Redirect → /receipt/{session_id}

    Driver->>App: GET /receipt/{session_id}
    App-->>Driver: Receipt page (session summary)

    Driver->>App: Tap "Download PDF" → GET /api/sessions/{session_id}/pdf
    App->>Core: GET /api/v1/public/sessions/{session_id}/pdf
    Core-->>App: PDF binary
    App-->>Driver: application/pdf download
```

### Key Routes

| Step | Route | Method |
|---|---|---|
| QR landing | `/c/{code}` | GET |
| Charger screen | `/charge/{cp_id}/{connector}` | GET |
| Create session | `/api/sessions/create` | POST |
| Live session | `/session/{session_id}` | GET |
| Poll status | `/api/sessions/{session_id}/poll` | GET |
| Stop session | `/api/sessions/{session_id}/stop` | POST |
| Receipt screen | `/receipt/{session_id}` | GET |
| Download PDF | `/api/sessions/{session_id}/pdf` | GET |

---

## 2. Account Flow

Drivers can register with a phone number (OTP), log in, view their charging history, and manage favorites.

```mermaid
sequenceDiagram
    actor Driver
    participant App as Charge App
    participant Core as Core API

    %% Registration
    Driver->>App: GET /account/register
    App-->>Driver: Register page (phone input)

    Driver->>App: POST /api/account/register {phone, name, email}
    App->>Core: POST /api/v1/public/account/register
    Core-->>App: {token, account}
    App-->>Driver: Set auth_token cookie → redirect /account/profile

    %% OTP Login
    Driver->>App: GET /account/login
    App-->>Driver: Login page (phone input)

    Driver->>App: POST /api/auth/send-otp {phone}
    App->>Core: POST /api/v1/public/auth/send-otp
    Core-->>App: {ok: true}
    App-->>Driver: OTP code input shown

    Driver->>App: POST /api/auth/verify-otp {phone, code}
    App->>Core: POST /api/v1/public/auth/verify-otp
    Core-->>App: {token} (JWT)
    App-->>Driver: Set auth_token cookie → redirect to charge flow

    %% View Profile
    Driver->>App: GET /account/profile
    Note over App: Middleware decodes auth_token cookie
    App->>Core: GET /api/v1/public/account/profile (Bearer token)
    Core-->>App: {name, email, phone, created_at}
    App-->>Driver: Profile page

    %% View History
    Driver->>App: GET /account/history
    App->>Core: GET /api/v1/public/account/sessions (Bearer token)
    Core-->>App: {sessions: [...], total_kwh, total_cost}
    App-->>Driver: History page (session list)

    %% Manage Favorites
    Driver->>App: POST /api/favorites/{cp_id}
    App->>Core: POST /api/v1/public/account/favorites/{cp_id} (Bearer token)
    Core-->>App: {ok: true}
    App-->>Driver: {ok: true, synced: true}

    %% Logout
    Driver->>App: POST /api/account/logout
    App-->>Driver: Delete auth_token cookie → {ok: true}
```

### Notes

- The `auth_token` cookie is HttpOnly and set with `SameSite=Lax`. Middleware decodes it on every request and populates `request.state.account`.
- If the JWT is expired or invalid, `request.state.account` is `None` and routes that require auth redirect to `/account/login`.
- Favorites also work without an account (localStorage-only). The server sync is additive when logged in.

---

## 3. Payment Flow

When payment is enabled (via feature flags), the flow includes a pre-authorization step via Mollie before the session starts.

```mermaid
sequenceDiagram
    actor Driver
    participant App as Charge App
    participant Core as Core API
    participant Mollie as PSP as Payment Provider

    Driver->>App: GET /charge/{cp_id}/{connector}
    App->>Core: GET /api/v1/chargers/{cp_id}
    Core-->>App: {tariff_kwh, preauth_amount: "€25"}
    App-->>Driver: Charge screen ("€25 pre-authorisation required")

    Driver->>App: POST /api/sessions/create {cp_id, connector, phone}
    App->>Core: POST /api/v1/public/sessions
    Core->>Mollie: Create payment (pre-auth, €25)
    Mollie-->>Core: {checkout_url, payment_id}
    Core-->>App: {payment_required: true, checkout_url}
    App-->>Driver: Redirect → Mollie checkout page

    Driver->>Mollie: Complete payment / link card
    Mollie-->>Core: Webhook: payment authorised
    Mollie-->>Driver: Redirect → /session/{session_id}

    Driver->>App: GET /session/{session_id}
    App->>Core: GET /api/v1/public/sessions/{session_id}
    Core-->>App: {status: "Charging", kwh: 0, cost: 0}
    App-->>Driver: Live session page

    loop Live updates
        Driver->>App: GET /api/sessions/{session_id}/poll
        App->>Core: GET /api/v1/public/sessions/{session_id}
        Core-->>App: {kwh, cost, power_kw, status}
        App-->>Driver: Running totals update
    end

    Driver->>App: POST /api/sessions/{session_id}/stop
    App->>Core: POST /api/v1/public/sessions/{session_id}/stop
    Core->>Mollie: Capture actual amount (kwh × tariff)
    Mollie-->>Core: {captured: true, amount}
    Core-->>App: {status: "Completed", final_cost}
    App-->>Driver: Redirect → /receipt/{session_id}

    Driver->>App: GET /api/sessions/{session_id}/pdf
    App->>Core: GET /api/v1/public/sessions/{session_id}/pdf
    Core-->>App: PDF (with payment reference, VAT, line items)
    App-->>Driver: Receipt PDF download
```

> **Note:** Mollie is the reference PSP implementation. Any payment provider can be integrated via Core API — the charge app only handles the redirect and webhook confirmation.

### Payment Feature Flag

Payment enforcement is controlled by a feature flag returned from Core API:

```json
{
  "flags": {
    "payment_required": true,
    "preauth_amount_eur": 25
  }
}
```

Templates check `flags.payment_required` to show or hide payment UI elements. The pre-authorisation amount is shown on the charge screen as a note before the driver starts.

### Session States

```
Pending → Preparing → Charging → Stopping → Completed
                                           ↘ Cancelled
```

- **Pending**: Session created, payment pending (if applicable)
- **Preparing**: Payment authorised, charger preparing
- **Charging**: Active charge in progress
- **Stopping**: Stop command sent, session wrapping up
- **Completed**: Session ended, final values recorded
- **Cancelled**: Session cancelled before charging started (no charge)
