# Charge App — Roadmap & Architecture Decisions

**Date:** March 27, 2026
**Decided by:** Ignacio

## Core Principles

1. **Web app (PWA)** — browser-based, all platforms, no native app
2. **One app, feature flags** — all features built in, toggled on/off from backend
3. **Logic is agnostic** — the charge app engine has no opinion about branding or features
4. **Skins are separate** — Operator skins apply branding. Engine is open-sourceable.
5. **Both B2B and public** — fleet drivers + general public use the same app
6. **Optional login** — anonymous OTP charging works. Account login is an opt-in feature for history/favorites/personalized receipts
7. **Roll out incrementally** — ship polished, enable features one by one

## Feature Flags

All features controlled by backend flags. Admin panel toggles them. App reads flags on load.

### Enabled (already working)
- `map` — Chargers on map with real-time status
- `otp_auth` — Phone verification via SMS
- `ideal_payment` — iDEAL via Mollie
- `live_session` — Real-time kW/kWh/SoC
- `remote_start` — Start charging via app
- `session_sms` — Recovery link via SMS

### Phase 1 — Launch Ready
- `pdf_receipt` — VAT-compliant PDF after every session (MANDATORY, not a flag)
- `charging_history` — My sessions (requires account or phone-based identity)
- `pwa_install` — Add to homescreen, service worker for offline session recovery
- `account_login` — Optional email/password account (enables history, favorites, email receipts)

### Phase 2 — Polish
- `push_notifications` — PWA push: charging complete, cable still connected
- `cost_estimator` — Estimated cost before starting
- `favorites` — Save chargers (requires account)
- `multi_language` — NL + EN
- `co2_savings` — CO₂ saved per session

### Phase 3 — Competitive
- `plug_and_charge` — ISO 15118, no app needed (PKI ready, needs Hubject)
- `rfid_card` — Order physical charge card
- `reservation` — Reserve a connector
- `loyalty_rewards` — Points/rewards program
- `roaming` — Charge at other networks via OCPI
- `route_planner` — Plan charging stops on route
- `carplay` — Not applicable to PWA (native only)
- `fleet_link` — Deep link to fleet portal

## Receipts (Mandatory — every session)

- Anonymous driver: PDF available via session link + SMS link
- Logged-in driver: PDF + emailed automatically with account details
- All receipts: VAT-compliant, operator details (configured via env), session data, tariff breakdown
- Format: proper PDF (reportlab or weasyprint), not plaintext

## Architecture (per architecture-v2.md section 19)

```
opencpo-charge-app/             (open-sourceable base)
├── main.py                     Engine — routes, API proxy, flag reader
├── templates/                  Base templates (clean, functional)
├── static/                     Base JS + CSS
├── plugins/                    Feature modules (each self-contained)
│   ├── history/                Charging history
│   ├── receipts/               PDF generation
│   ├── estimator/              Cost estimator
│   ├── favorites/              Saved chargers
│   ├── account/                Optional login system
│   └── push/                   Push notifications
└── skins/
    └── skins/                  Per-operator branded skins (CSS/animations)
```

Open-source base: functional, clean UX, no branding
Each operator: their own skin, same engine
Other operators: their own skin, same engine

## User Identity Model

- **Anonymous:** OTP per session → phone number used as soft identity
- **Account (optional):** email + password → links all sessions, enables history/favorites/email receipts
- Phone number links anonymous sessions to account retroactively ("we found 3 previous sessions on this number")

## Build Order

1. Feature flag system (Core API table + Admin panel + charge app reader)
2. PDF receipts (mandatory, every session)
3. PWA manifest + service worker
4. Optional account system
5. Charging history (phone-based first, then account-based)
6. Cost estimator
7. Push notifications
8. Everything else per Phase 2/3
