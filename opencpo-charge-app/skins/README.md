# OpenCPO Charge App — Skin Library

Community-contributed skins for the OpenCPO charge app. Each skin is a complete visual theme that can be applied with a single environment variable.

## Available Skins

| Skin | Mode | Primary | Vibe | Preview |
|------|------|---------|------|---------|
| **voltage-backstage** | Dark | Ice Blue `#6FD2FF` | Stage lighting, atmospheric | [Built-in] |
| **voltage-backstage** | Dark | Ice Blue `#6FD2FF` | Stage lighting, atmospheric | [6 screens] |
| **stroom-electron** | Dark | Lime Green `#9EDA2D` | Editorial lifestyle, electric | [12 screens] |
| **ion-flux** | Dark | Neon Cyan `#81ECFF` | Obsidian HUD, carbon fiber | [8 screens] |
| **current-flow** | ☀️ Light | Teal `#006686` | Clean Dutch editorial, daytime | [6 screens] |
| **voltage-industrial** | Dark | Electric Blue `#00DAF3` | SCADA terminal, HMI | [5 screens] |
| **default** | Dark | Blue `#2563EB` | Clean generic, no branding | [Built-in] |

## Quick Start

### Use an existing skin
```bash
# Set the SKIN environment variable
export SKIN=voltage-backstage

# Or in your .env file
SKIN=voltage-backstage
```

The charge app resolves templates and CSS in this order:
1. `skins/{SKIN}/templates/` → skin template overrides
2. `skins/{SKIN}/static/style.css` → served at `/skin/style.css`
3. `templates/` → base templates (fallback)
4. `static/` → base static assets (fallback)

### Create your own skin

#### Option A: Use Google Stitch (recommended)

1. **Open [Google Stitch](https://stitch.withgoogle.com)**
2. **Use this prompt** (customize the brand details):

```
Design a mobile EV charging app for [YOUR BRAND], a charge point operator.
Core screens: Map with charger pins, QR scanner, Charger Detail (status badge,
connector type CCS2, kW rating, step-by-step charging guide, pricing per kWh),
OTP phone verification, Live Charging Session (real-time kW power gauge, kWh
delivered, cost in euros, SoC battery bar, duration timer, stop button),
Receipt (energy delivered, tariff breakdown with 21% BTW, PDF download).
Design system: [YOUR COLORS AND STYLE]. Bottom navigation: Map, Scan, Account.
[YOUR LANGUAGE] UI. PWA mobile-first, 390px width.
```

3. **Export the zip** from Stitch
4. **Run the converter**:
```bash
python tools/stitch-to-skin.py exported.zip my-brand-name --output-dir skins/
```

5. **Test it**:
```bash
SKIN=my-brand-name python main.py
```

#### Option B: Manual skin creation

Create a directory under `skins/` with this structure:

```
skins/my-skin/
├── skin.json              # Required: metadata + color tokens
├── static/
│   └── style.css          # Required: complete CSS theme
├── templates/             # Optional: template overrides
│   ├── home.html          # Override any base template
│   ├── charge.html
│   └── ...
├── DESIGN.md              # Optional: design system documentation
└── previews/              # Optional: screen preview images
    ├── map.png
    ├── session.png
    └── ...
```

### skin.json format

```json
{
  "name": "My Custom Skin",
  "version": "1.0",
  "mode": "dark",
  "colors": {
    "primary": "#00B0E4",
    "secondary": "#84BD00",
    "background": "#0a1628",
    "card": "#0f2035",
    "border": "#1a3a5c"
  },
  "fonts": {
    "headline": "Space Grotesk",
    "body": "Inter",
    "label": "Space Grotesk",
    "mono": "'Roboto Mono', monospace"
  },
  "logo": "logo.svg",
  "favicon": "favicon.svg"
}
```

### CSS Custom Properties

Your `style.css` must define these CSS custom properties in `:root`:

| Variable | Description | Example (dark) | Example (light) |
|----------|-------------|----------------|-----------------|
| `--bg` | Page background | `#0a1929` | `#f8fafb` |
| `--bg2` | Secondary background | `#0d2137` | `#f2f4f5` |
| `--bg3` | Tertiary background / input bg | `#132f4c` | `#e8eaeb` |
| `--card` | Card background | `#0d2137` | `#ffffff` |
| `--border` | Border color | `#1e3a5f` | `#dde3e8` |
| `--accent` | Primary action color | `#00B0E4` | `#006686` |
| `--accent2` | Primary gradient end | `#0090c0` | `#00B0E4` |
| `--on-accent` | Text on accent buttons | `#003547` | `#ffffff` |
| `--green` | Success / available | `#22c55e` | `#476800` |
| `--red` | Error / danger | `#ef4444` | `#ba1a1a` |
| `--yellow` | Warning / preparing | `#eab308` | `#7c5800` |
| `--text` | Primary text | `#f1f5f9` | `#191c1d` |
| `--text2` | Secondary text | `#94a3b8` | `#5f6b72` |
| `--text3` | Muted text | `#64748b` | `#8d979e` |
| `--radius` | Card border radius | `16px` | `16px` |
| `--radius-sm` | Button/input radius | `10px` | `10px` |
| `--font-headline` | Headlines | `'Space Grotesk'` | `'Manrope'` |
| `--font-body` | Body text | `'Manrope'` | `'Inter'` |
| `--font-label` | Labels & badges | `'Space Grotesk'` | `'Inter'` |
| `--font-mono` | Monospace numbers | `'Roboto Mono'` | `'Roboto Mono'` |

### CSS Classes Reference

Your skin CSS should style these classes (the base templates use them):

**Layout:** `.screen`, `.page-content`, `.app-header`, `.app-footer`
**Charger:** `.charger-card`, `.charger-title`, `.status-badge`, `.status-badge.available/.preparing/.occupied`
**Rate:** `.rate-display`, `.rate-value`, `.rate-label`
**Steps:** `.step-guide`, `.step-item`, `.step-icon`, `.step-title`, `.step-desc`
**Buttons:** `.btn`, `.btn-primary`, `.btn-danger`, `.btn-outline`, `.btn-ghost`, `.btn-pdf`
**Forms:** `.form-group`, `.form-label`, `.form-input`
**Session:** `.power-display`, `.power-value`, `.power-unit`, `.session-stats`, `.stat-row`, `.stat-label`, `.stat-value`
**SoC:** `.soc-bar`, `.soc-fill`, `.soc-text`
**Receipt:** `.receipt-card`, `.receipt-header`, `.receipt-row`, `.receipt-row.total`
**Map:** `.home-screen`, `.map-geo-btn`, `.map-zoom-btn`, `.map-bottom-sheet`, `.sheet-handle`
**Misc:** `.info-note`, `.error-card`, `.live-indicator`, `.live-dot`, `.spinner`

## Stitch-to-Skin Converter

The `tools/stitch-to-skin.py` script automates skin creation from Google Stitch exports.

### What it does:
1. Parses the Tailwind config embedded in Stitch HTML files
2. Extracts color tokens, font families, and border-radius values
3. Maps Stitch's Material Design tokens to OpenCPO CSS custom properties
4. Generates a complete `skin.json` + `style.css`
5. Copies screen previews and design documentation

### Usage:
```bash
# From a zip export
python tools/stitch-to-skin.py my-stitch-export.zip my-skin-name

# From an unpacked directory
python tools/stitch-to-skin.py ./stitch-output/ my-skin-name

# Custom output directory
python tools/stitch-to-skin.py export.zip my-skin --output-dir ./custom-skins/
```

### After conversion:
- Review `skin.json` — adjust colors if needed
- Review `static/style.css` — the converter maps ~95% of styles automatically
- Add your `logo.svg` and `favicon.svg` to `static/`
- Test with `SKIN=my-skin-name python main.py`

## Stitch Prompt Tips

For best results, include these details in your Stitch prompt:

1. **All core screens**: Map, QR scanner, Charger Detail, OTP verification, Live Session, Receipt
2. **Real data points**: kW, kWh, €/kWh, BTW percentage, SoC%, duration
3. **Your brand colors**: Specific hex values for primary, secondary, background
4. **Typography preference**: "monospace for data", "editorial feel", "industrial HMI"
5. **PWA constraint**: "390px mobile-first" keeps it phone-sized
6. **Language**: "Dutch language UI" or "English language UI"
7. **Mode**: "Dark mode" or "Light mode" (or both)

### Example prompts by style:

**Premium Dark:**
> Design a mobile EV charging app for [BRAND]. Dark navy (#0a1929) background, electric cyan (#00B0E4) accent. Theater-grade reliability aesthetic. Space Grotesk headings, Manrope body. Glow effects on active states.

**Clean Light:**
> Design a mobile EV charging app for [BRAND]. Light mode, white background, teal (#006686) primary. Clean Dutch editorial feel. Manrope headings, Inter body. Soft shadows, eco-green accents.

**Industrial:**
> Design a mobile EV charging app for [BRAND]. Near-black (#131313) background, neon cyan (#00DAF3) accent. HMI/SCADA terminal aesthetic. Monospace numbers, sharp corners, underscore naming.

## Contributing

1. Create your skin using Stitch or manually
2. Test it with the charge app
3. Submit a PR with your skin directory under `skins/`
4. Include `skin.json`, `style.css`, `DESIGN.md`, and preview screenshots

## License

Skins in this library are MIT licensed. You're free to use, modify, and redistribute them.
