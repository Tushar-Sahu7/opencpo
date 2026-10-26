# Navigation Redesign — Charge App

## Problem
- Logo not clickable (no way home)
- Login overlaps map controls
- Language flags overlap map controls
- No back button on sub-pages
- Account pages have no navigation out
- Center tab is brand logo (wasted space)
- Stuck sessions trap the user

## Design

### Bottom Navigation Bar (all pages)
```
┌────────────────────────────────────────┐
│  🗺 Map    📱 Scan    👤 Account       │
└────────────────────────────────────────┘
```
- 3 tabs: Map, Scan, Account
- Always visible on every page
- Active tab highlighted with accent color
- Account tab shows user icon (logged in) or generic icon (not logged in)
- Account tab → /account/profile if logged in, /account/login if not
- If account_login flag is OFF, still show Account tab but it goes to a simple settings page (language switch at minimum)

### Top Bar (sub-pages only, NOT on map)
On charge screen, auth, session, receipt, profile, history:
```
┌────────────────────────────────────────┐
│  ← Back    ⚡ OpenCPO             │
└────────────────────────────────────────┘
```
- Left: back arrow → previous page or home
- Center: logo text (clickable → home)
- NO floating elements over the map

### Map Page (home)
- Full-screen map (current)
- Bottom nav bar (replaces current tab-bar)
- NO language flags on map (moved to Account/Settings)
- NO login button floating on map
- Location prompt → auto-dismiss after granted or 5s timeout

### Language Switcher
- Moved to Account/Settings page
- NOT on the map, NOT floating
- Simple: 🇳🇱 Nederlands / 🇬🇧 English radio buttons or toggle

### Session Page — Escape Hatch
- If session is stuck >90s in "starting" state → show:
  - "Charger is not responding" message
  - "Cancel & return to map" button
  - Auto-cancel after 3 minutes
- Cancel clears localStorage.active_session_id
- Bottom nav still visible → user can always tap Map to escape

### Implementation
1. Move bottom nav to base.html (shared across ALL pages)
2. Remove floating login/language from base.html  
3. Add top-bar partial for sub-pages
4. Language switcher → Account/Settings page
5. Session timeout logic in session.html JS
