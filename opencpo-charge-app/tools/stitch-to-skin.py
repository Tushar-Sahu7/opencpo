#!/usr/bin/env python3
"""
stitch-to-skin — Convert a Google Stitch export to an OpenCPO charge app skin.

Usage:
    python stitch-to-skin.py <stitch-zip-or-dir> <skin-name> [--output-dir skins/]

Takes a Stitch export (zip or unpacked directory) and produces:
    skins/<skin-name>/
        skin.json       — Metadata, color tokens, font stacks
        static/
            style.css   — Complete CSS skin mapped to charge app classes

The tool parses the Tailwind config embedded in Stitch HTML files to extract
design tokens (colors, fonts, border-radius) and maps them to the charge app's
CSS custom property system.
"""

import argparse
import json
import os
import re
import sys
import zipfile
import tempfile
from pathlib import Path


# ── Token extraction ──────────────────────────────────────────────────────

def extract_tailwind_config(html_content: str) -> dict | None:
    """Extract the tailwind.config JS object from a Stitch HTML file."""
    # Find the script block with tailwind config
    match = re.search(
        r'tailwind\.config\s*=\s*(\{.*?\})\s*\n\s*</script>',
        html_content,
        re.DOTALL
    )
    if not match:
        return None

    js_obj = match.group(1)

    # Convert JS object to valid JSON:
    # 1. Add quotes around unquoted keys
    # 2. Remove trailing commas
    # 3. Handle special cases

    # Remove JS comments
    js_obj = re.sub(r'//.*?\n', '\n', js_obj)
    js_obj = re.sub(r'/\*.*?\*/', '', js_obj, flags=re.DOTALL)

    # Quote unquoted keys (word chars followed by colon)
    js_obj = re.sub(r'(\s)(\w[\w-]*)\s*:', r'\1"\2":', js_obj)

    # Remove trailing commas before } or ]
    js_obj = re.sub(r',\s*([}\]])', r'\1', js_obj)

    # Try to parse
    try:
        return json.loads(js_obj)
    except json.JSONDecodeError as e:
        # Fallback: extract just the colors, fonts, borderRadius with regex
        return extract_tokens_regex(html_content)


def extract_tokens_regex(html_content: str) -> dict:
    """Fallback: extract design tokens with regex when JSON parse fails."""
    result = {"theme": {"extend": {}}}
    extend = result["theme"]["extend"]

    # Extract colors
    colors_match = re.search(
        r'"colors"\s*:\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}',
        html_content,
        re.DOTALL
    )
    if colors_match:
        colors_str = "{" + colors_match.group(1) + "}"
        # Clean up
        colors_str = re.sub(r',\s*\}', '}', colors_str)
        try:
            extend["colors"] = json.loads(colors_str)
        except json.JSONDecodeError:
            # Extract individual color entries
            colors = {}
            for m in re.finditer(r'"([^"]+)"\s*:\s*"(#[0-9a-fA-F]{3,8})"', colors_match.group(1)):
                colors[m.group(1)] = m.group(2)
            extend["colors"] = colors

    # Extract fontFamily
    font_match = re.search(
        r'"fontFamily"\s*:\s*\{([^}]+)\}',
        html_content
    )
    if font_match:
        fonts = {}
        for m in re.finditer(r'"(\w+)"\s*:\s*\["([^"]+)"\]', font_match.group(1)):
            fonts[m.group(1)] = m.group(2)
        extend["fontFamily"] = fonts

    # Extract borderRadius
    radius_match = re.search(
        r'"borderRadius"\s*:\s*\{([^}]+)\}',
        html_content
    )
    if radius_match:
        radii = {}
        for m in re.finditer(r'"(\w+)"\s*:\s*"([^"]+)"', radius_match.group(1)):
            radii[m.group(1)] = m.group(2)
        extend["borderRadius"] = radii

    return result


def extract_custom_css(html_content: str) -> str:
    """Extract custom <style> blocks (non-tailwind) from Stitch HTML."""
    styles = []
    for match in re.finditer(r'<style[^>]*>(.*?)</style>', html_content, re.DOTALL):
        css = match.group(1).strip()
        # Skip the tailwind config script and minimal body height rules
        if 'tailwind.config' in css or css.startswith('body {') and 'min-height' in css:
            continue
        if css and len(css) > 20:
            styles.append(css)
    return '\n'.join(styles)


# ── Token mapping ─────────────────────────────────────────────────────────

# Map Stitch/Material color tokens to our CSS custom properties
STITCH_TO_CSS_MAP = {
    # Backgrounds
    'background': '--bg',
    'surface': '--bg',
    'surface-dim': '--bg',
    'surface-container-lowest': '--bg-deep',
    'surface-container-low': '--bg2',
    'surface-container': '--bg2',
    'surface-container-high': '--bg3',
    'surface-container-highest': '--card',
    'surface-bright': '--card-hover',
    'surface-variant': '--card',

    # Text
    'on-surface': '--text',
    'on-surface-variant': '--text2',
    'on-background': '--text',

    # Primary
    'primary': '--accent',
    'primary-container': '--accent2',
    'primary-fixed-dim': '--accent',
    'on-primary': '--on-accent',
    'on-primary-container': '--on-accent',

    # Secondary
    'secondary': '--green',
    'secondary-container': '--green-bright',
    'secondary-fixed-dim': '--green',
    'on-secondary': '--on-green',

    # Error
    'error': '--red',
    'error-container': '--red-dim',

    # Borders
    'outline': '--border-strong',
    'outline-variant': '--border',

    # Tertiary
    'tertiary': '--tertiary',
    'tertiary-container': '--tertiary-dim',
}


def map_colors(stitch_colors: dict) -> dict:
    """Map Stitch color tokens to CSS custom properties."""
    css_vars = {}
    for stitch_key, css_var in STITCH_TO_CSS_MAP.items():
        if stitch_key in stitch_colors:
            css_vars[css_var] = stitch_colors[stitch_key]
    return css_vars


def determine_mode(colors: dict) -> str:
    """Determine if the skin is dark or light based on background color."""
    bg = colors.get('background', colors.get('surface', '#000000'))
    # Parse hex to check luminance
    bg = bg.lstrip('#')
    if len(bg) == 3:
        bg = ''.join(c * 2 for c in bg)
    try:
        r, g, b = int(bg[0:2], 16), int(bg[2:4], 16), int(bg[4:6], 16)
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return 'light' if luminance > 0.5 else 'dark'
    except (ValueError, IndexError):
        return 'dark'


# ── CSS generation ────────────────────────────────────────────────────────

def generate_skin_json(skin_name: str, colors: dict, fonts: dict, mode: str) -> dict:
    """Generate skin.json metadata."""
    # Pick the most relevant colors for the simplified skin.json
    return {
        "name": skin_name,
        "version": "1.0",
        "mode": mode,
        "colors": {
            "primary": colors.get('primary', '#00B0E4'),
            "secondary": colors.get('secondary', '#84BD00'),
            "background": colors.get('background', colors.get('surface', '#0a1628')),
            "card": colors.get('surface-container-highest',
                              colors.get('surface-container-high', '#0f2035')),
            "border": colors.get('outline-variant',
                                colors.get('outline', '#1a3a5c'))
        },
        "fonts": {
            "headline": fonts.get('headline', 'system-ui'),
            "body": fonts.get('body', 'system-ui'),
            "label": fonts.get('label', fonts.get('headline', 'system-ui')),
            "mono": fonts.get('mono', "'SF Mono', 'Fira Code', 'Roboto Mono', monospace")
        },
        "logo": "logo.svg",
        "favicon": "favicon.svg"
    }


def generate_style_css(css_vars: dict, stitch_colors: dict, fonts: dict,
                       radii: dict, mode: str, custom_css: str) -> str:
    """Generate the complete style.css for the skin."""

    # Build font import URL
    font_names = set()
    for f in fonts.values():
        if f and f not in ('system-ui', 'monospace'):
            font_names.add(f)

    font_import = ''
    if font_names:
        families = '&family='.join(
            f.replace(' ', '+') + ':wght@300;400;500;600;700'
            for f in sorted(font_names)
        )
        font_import = f"@import url('https://fonts.googleapis.com/css2?family={families}&display=swap');\n\n"

    # Determine text colors for light vs dark
    text_muted = css_vars.get('--text2', '#94a3b8')
    text_dim = css_vars.get('--text3', stitch_colors.get('outline', '#64748b'))

    # Build :root variables
    root_vars = []
    root_vars.append(f"  --bg: {css_vars.get('--bg', '#0a1929')};")
    root_vars.append(f"  --bg2: {css_vars.get('--bg2', '#0d2137')};")
    root_vars.append(f"  --bg3: {css_vars.get('--bg3', '#132f4c')};")
    root_vars.append(f"  --bg-deep: {css_vars.get('--bg-deep', css_vars.get('--bg', '#000'))};")
    root_vars.append(f"  --card: {css_vars.get('--card', '#0d2137')};")
    root_vars.append(f"  --card-hover: {css_vars.get('--card-hover', css_vars.get('--bg3', '#1a2d45'))};")
    root_vars.append(f"  --border: {css_vars.get('--border', '#1e3a5f')};")
    root_vars.append(f"  --border-strong: {css_vars.get('--border-strong', css_vars.get('--border', '#3d484f'))};")
    root_vars.append(f"  --accent: {css_vars.get('--accent', '#00B0E4')};")
    root_vars.append(f"  --accent2: {css_vars.get('--accent2', '#0090c0')};")
    root_vars.append(f"  --on-accent: {css_vars.get('--on-accent', '#003547')};")
    root_vars.append(f"  --green: {css_vars.get('--green', '#22c55e')};")
    root_vars.append(f"  --green-bright: {css_vars.get('--green-bright', css_vars.get('--green', '#22c55e'))};")
    root_vars.append(f"  --red: {css_vars.get('--red', '#ef4444')};")
    root_vars.append(f"  --yellow: {stitch_colors.get('tertiary', '#eab308')};")
    root_vars.append(f"  --text: {css_vars.get('--text', '#f1f5f9')};")
    root_vars.append(f"  --text1: {css_vars.get('--text', '#f1f5f9')};")
    root_vars.append(f"  --text2: {text_muted};")
    root_vars.append(f"  --text3: {text_dim};")

    # Border radius
    r_default = radii.get('DEFAULT', '0.125rem') if radii else '0.125rem'
    r_sm = radii.get('sm', radii.get('lg', '0.25rem')) if radii else '10px'
    r_lg = radii.get('xl', radii.get('full', '0.5rem')) if radii else '16px'

    root_vars.append(f"  --radius: {r_lg};")
    root_vars.append(f"  --radius-sm: {r_sm};")

    # Font families
    headline_font = fonts.get('headline', 'system-ui')
    body_font = fonts.get('body', 'system-ui')
    label_font = fonts.get('label', headline_font)
    mono_font = fonts.get('mono', "'SF Mono', 'Fira Code', 'Roboto Mono', monospace")

    root_vars.append(f"  --font-headline: '{headline_font}', system-ui, sans-serif;")
    root_vars.append(f"  --font-body: '{body_font}', system-ui, sans-serif;")
    root_vars.append(f"  --font-label: '{label_font}', system-ui, sans-serif;")
    root_vars.append(f"  --font-mono: {mono_font};")

    root_block = '\n'.join(root_vars)

    # Card2 (transparent overlay)
    card2_color = 'rgba(255,255,255,0.05)' if mode == 'dark' else 'rgba(0,0,0,0.04)'

    css = f"""{font_import}/* OpenCPO Charge App Skin — Auto-generated from Stitch export */
/* Generator: stitch-to-skin v1.0 */

*, *::before, *::after {{
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}}

:root {{
{root_block}
  --card2: {card2_color};
}}

html, body {{
  height: 100%;
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-body);
  font-size: 16px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}}

#app {{
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
}}

/* ── Screens ── */

.screen {{
  display: none;
  flex-direction: column;
  min-height: 100dvh;
  padding: env(safe-area-inset-top, 0) 0 env(safe-area-inset-bottom, 0);
}}

.screen.active {{
  display: flex;
}}

/* ── Loading ── */

#loading {{
  align-items: center;
  justify-content: center;
}}

.loading-inner {{
  text-align: center;
}}

.logo-img {{
  height: 48px;
  width: auto;
  display: block;
  object-fit: contain;
  margin: 0 auto;
  filter: drop-shadow(0 0 12px {css_vars.get('--accent', '#00B0E4')}40);
}}

.spinner {{
  width: 36px;
  height: 36px;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 0 auto;
}}

@keyframes spin {{
  to {{ transform: rotate(360deg); }}
}}

/* ── Header ── */

.app-header {{
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 28px 20px 20px;
  border-bottom: 1px solid var(--border);
  text-align: center;
  background: linear-gradient(180deg, var(--bg2) 0%, var(--bg) 100%);
}}

.header-subtitle {{
  font-size: 12px;
  color: var(--text3);
  margin-top: 2px;
  font-family: var(--font-label);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}}

.app-footer {{
  text-align: center;
  padding: 16px 20px;
  font-size: 12px;
  color: var(--text3);
  border-top: 1px solid var(--border);
}}

.app-footer a {{
  color: var(--text3);
  text-decoration: none;
}}

/* ── Page content ── */

.page-content {{
  flex: 1;
  padding: 24px 20px;
  max-width: 480px;
  margin: 0 auto;
  width: 100%;
}}

/* ── Charger card ── */

.charger-card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
  margin-bottom: 16px;
}}

.charger-location {{
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}}

.location-icon {{
  font-size: 18px;
}}

.location-name {{
  font-size: 16px;
  font-weight: 600;
  color: var(--text2);
  font-family: var(--font-label);
}}

.charger-title {{
  font-size: 24px;
  font-weight: 700;
  margin-bottom: 12px;
  color: var(--text);
  font-family: var(--font-headline);
}}

.status-badge {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  padding: 4px 12px;
  border-radius: 20px;
  margin-bottom: 20px;
  font-family: var(--font-label);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}}

.status-badge.available {{
  background: {css_vars.get('--green', '#22c55e')}26;
  color: var(--green);
  border: 1px solid {css_vars.get('--green', '#22c55e')}4d;
}}

.status-badge.preparing {{
  background: var(--yellow, #eab308)26;
  color: var(--yellow);
  border: 1px solid var(--yellow, #eab308)4d;
}}

.status-badge.occupied {{
  background: {css_vars.get('--accent', '#00B0E4')}26;
  color: var(--accent);
  border: 1px solid {css_vars.get('--accent', '#00B0E4')}4d;
}}

.status-badge.loading {{
  background: var(--yellow, #eab308)26;
  color: var(--yellow);
  border: 1px solid var(--yellow, #eab308)4d;
}}

/* ── Rate display ── */

.rate-display {{
  background: var(--bg3);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 16px;
  margin-bottom: 16px;
  text-align: center;
}}

.rate-value {{
  font-size: 36px;
  font-weight: 800;
  color: var(--accent);
  line-height: 1.1;
  font-family: var(--font-headline);
}}

.rate-label {{
  font-size: 13px;
  color: var(--text2);
  margin-top: 4px;
  font-family: var(--font-label);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}}

.rate-note {{
  font-size: 11px;
  color: var(--text3);
  margin-top: 4px;
}}

/* ── Step guide ── */

.step-guide {{
  margin: 16px 0;
  padding: 14px 16px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}}

.step-item {{
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 0;
  opacity: 0.4;
  transition: opacity 0.3s;
}}

.step-item + .step-item {{
  margin-top: 8px;
}}

.step-item.active {{
  opacity: 1;
}}

.step-item.done {{
  opacity: 0.5;
}}

.step-icon {{
  font-size: 20px;
  flex-shrink: 0;
}}

.step-title {{
  font-size: 13px;
  font-weight: 600;
  color: var(--text1);
  font-family: var(--font-label);
}}

.step-desc {{
  font-size: 12px;
  color: var(--text3);
}}

/* ── Info note ── */

.info-note {{
  background: {css_vars.get('--accent', '#00B0E4')}14;
  border: 1px solid {css_vars.get('--accent', '#00B0E4')}33;
  border-radius: var(--radius-sm);
  padding: 12px 14px;
  font-size: 13px;
  color: var(--text2);
  margin-bottom: 20px;
  line-height: 1.5;
}}

.info-note strong {{
  color: var(--accent);
}}

/* ── Buttons ── */

.btn {{
  display: block;
  width: 100%;
  padding: 16px;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 16px;
  font-weight: 700;
  cursor: pointer;
  text-align: center;
  text-decoration: none;
  transition: opacity 0.15s, transform 0.1s;
  font-family: var(--font-headline);
  letter-spacing: 0.02em;
}}

.btn:active {{
  transform: scale(0.98);
}}

.btn-primary {{
  background: linear-gradient(135deg, var(--accent), var(--accent2));
  color: var(--on-accent);
}}

.btn-primary:disabled {{
  opacity: 0.5;
  cursor: not-allowed;
}}

.btn-primary.btn-ready {{
  background: linear-gradient(135deg, {css_vars.get('--green', '#22c55e')}, {css_vars.get('--green-bright', '#22c55e')});
}}

.btn-danger {{
  background: linear-gradient(135deg, #dc2626, var(--red));
  color: white;
}}

.btn-outline {{
  background: transparent;
  color: var(--accent);
  border: 1px solid var(--accent);
}}

.btn-ghost {{
  background: transparent;
  color: var(--text2);
  font-size: 14px;
  font-weight: 500;
}}

.btn-pdf {{
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 16px;
  padding: 14px;
  border-radius: 12px;
  background: {css_vars.get('--accent', '#00B0E4')}1a;
  border: 1px solid {css_vars.get('--accent', '#00B0E4')}4d;
  color: var(--accent);
  text-decoration: none;
  font-weight: 600;
  font-size: 15px;
  font-family: var(--font-headline);
}}

/* ── Form ── */

.form-group {{
  margin-bottom: 16px;
}}

.form-label {{
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--text2);
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-family: var(--font-label);
}}

.form-input {{
  display: block;
  width: 100%;
  padding: 14px 16px;
  background: var(--bg3);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text);
  font-size: 16px;
  outline: none;
  transition: border-color 0.15s;
}}

.form-input:focus {{
  border-color: var(--accent);
  box-shadow: 0 0 0 2px {css_vars.get('--accent', '#00B0E4')}26;
}}

.form-input::placeholder {{
  color: var(--text3);
}}

/* ── Live session ── */

.power-display {{
  background: var(--bg3);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 40px 20px;
  margin-bottom: 16px;
  text-align: center;
}}

.power-value {{
  font-size: 80px;
  font-weight: 900;
  background: linear-gradient(135deg, var(--accent), var(--green));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  font-family: var(--font-headline);
}}

.power-unit {{
  font-size: 20px;
  color: var(--text2);
  margin-top: 4px;
  font-family: var(--font-label);
  text-transform: uppercase;
  letter-spacing: 0.1em;
}}

.session-stats {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  margin-bottom: 20px;
}}

.stat-row {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}}

.stat-row:last-child {{
  border-bottom: none;
}}

.stat-label {{
  font-size: 14px;
  color: var(--text2);
  font-family: var(--font-label);
}}

.stat-value {{
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
  font-variant-numeric: tabular-nums;
}}

.stat-value.mono {{
  font-family: var(--font-mono);
}}

/* ── SoC battery bar ── */

.soc-bar {{
  position: relative;
  height: 40px;
  background: var(--bg3);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
  margin-bottom: 16px;
}}

.soc-fill {{
  height: 100%;
  background: linear-gradient(90deg, {css_vars.get('--green', '#16a34a')}, {css_vars.get('--green-bright', '#22c55e')});
  border-radius: var(--radius-sm) 0 0 var(--radius-sm);
  transition: width 1s ease;
}}

.soc-text {{
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 700;
  color: white;
  text-shadow: 0 1px 3px rgba(0,0,0,0.5);
  font-family: var(--font-headline);
}}

/* ── Receipt ── */

.receipt-card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
  margin-bottom: 16px;
}}

.receipt-header {{
  text-align: center;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
}}

.receipt-title {{
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 4px;
  font-family: var(--font-headline);
}}

.receipt-subtitle {{
  font-size: 13px;
  color: var(--text2);
}}

.receipt-row {{
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  font-size: 14px;
  border-bottom: 1px solid {css_vars.get('--border', '#1e3a5f')}33;
}}

.receipt-row:last-child {{
  border-bottom: none;
}}

.receipt-row.total {{
  font-size: 18px;
  font-weight: 700;
  padding-top: 12px;
  margin-top: 4px;
  border-top: 1px solid var(--border);
  color: var(--accent);
  font-family: var(--font-headline);
}}

.receipt-row .label {{
  color: var(--text2);
}}

.receipt-row .value {{
  font-weight: 600;
  color: var(--text);
}}

.success-icon {{
  font-size: 48px;
  margin-bottom: 12px;
}}

/* ── Map & Tab Layout ── */

.hidden {{ display: none !important; }}
.home-screen {{ display: flex; flex-direction: column; height: 100dvh; }}
.home-tab-content {{ flex: 1; position: relative; overflow: hidden; }}
#charger-map {{ width: 100%; height: 100%; position: absolute; top: 0; left: 0; }}

.bottom-tab-bar {{
  display: flex;
  align-items: center;
  border-top: 1px solid var(--border);
  background: var(--bg2);
  padding: 8px 0 env(safe-area-inset-bottom, 8px);
  z-index: 100;
}}

.bottom-tab {{
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 8px;
  background: none;
  border: none;
  color: var(--text3);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: color 0.15s;
  font-family: var(--font-label);
}}

.bottom-tab.active {{ color: var(--accent); }}

/* ── Map controls ── */

.map-geo-btn {{
  position: absolute;
  bottom: 100px;
  right: 12px;
  z-index: 1100;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: var(--bg2);
  border: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}}

.map-zoom-controls {{
  position: absolute;
  bottom: 160px;
  right: 12px;
  z-index: 1100;
  display: flex;
  flex-direction: column;
  gap: 4px;
}}

.map-zoom-btn {{
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: var(--bg2);
  border: 1px solid var(--border);
  color: var(--text);
  font-size: 20px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}}

.theme-toggle {{
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 1100;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--bg2);
  border: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}}

/* ── Bottom sheet ── */

.map-bottom-sheet {{
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: var(--bg2);
  border-top: 1px solid var(--border);
  border-radius: var(--radius) var(--radius) 0 0;
  padding: 0;
  transform: translateY(100%);
  transition: transform 0.3s ease;
  z-index: 1200;
  max-height: 60vh;
  overflow-y: auto;
}}

.map-bottom-sheet.open {{
  transform: translateY(0);
  padding: 16px 20px 24px;
}}

.sheet-handle {{
  width: 36px;
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  margin: 0 auto 12px;
}}

.sheet-charger-name {{
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 4px;
  font-family: var(--font-headline);
}}

.sheet-charger-addr {{
  font-size: 13px;
  color: var(--text2);
  margin-bottom: 8px;
}}

.sheet-btn {{
  flex: 1;
  padding: 10px 16px;
  border-radius: 8px;
  border: none;
  font-size: 14px;
  font-weight: 600;
  text-align: center;
  text-decoration: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}}

.sheet-btn-nav {{
  background: var(--accent);
  color: var(--on-accent);
}}

/* ── Session charger info ── */

.session-charger-info {{
  text-align: center;
  margin-bottom: 16px;
  padding: 12px;
  background: var(--bg3);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}}

.session-charger-name {{
  font-size: 16px;
  font-weight: 700;
  font-family: var(--font-headline);
}}

.session-charger-detail {{
  font-size: 12px;
  color: var(--text3);
  margin-top: 2px;
  font-family: var(--font-label);
}}

/* ── Error ── */

.error-card {{
  background: {css_vars.get('--red', '#ef4444')}1a;
  border: 1px solid {css_vars.get('--red', '#ef4444')}4d;
  border-radius: var(--radius-sm);
  padding: 14px 16px;
  color: var(--red);
  font-size: 14px;
  margin-bottom: 16px;
}}

/* ── Utility ── */

.mt-8 {{ margin-top: 8px; }}
.mt-16 {{ margin-top: 16px; }}
.mt-24 {{ margin-top: 24px; }}
.mb-8 {{ margin-bottom: 8px; }}
.text-center {{ text-align: center; }}
.text-muted {{ color: var(--text2); font-size: 13px; }}
.divider {{ height: 1px; background: var(--border); margin: 16px 0; }}

/* ── Live indicator ── */

@keyframes pulse-green {{
  0%, 100% {{ opacity: 1; }}
  50% {{ opacity: 0.6; }}
}}

.live-indicator {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--green);
  font-weight: 600;
  margin-bottom: 8px;
  font-family: var(--font-label);
  text-transform: uppercase;
  letter-spacing: 0.1em;
}}

.live-dot {{
  width: 8px;
  height: 8px;
  background: var(--green);
  border-radius: 50%;
  animation: pulse-green 1.5s ease-in-out infinite;
}}

/* ── Animations ── */

@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }}
}}

html {{ scroll-behavior: smooth; }}

@keyframes fadeSlideUp {{
  from {{ opacity: 0; transform: translateY(16px); }}
  to {{ opacity: 1; transform: translateY(0); }}
}}

.page-content {{
  animation: fadeSlideUp 0.35s ease-out;
}}

@keyframes cardEntry {{
  from {{ opacity: 0; transform: translateY(30px) scale(0.97); }}
  to {{ opacity: 1; transform: translateY(0) scale(1); }}
}}

.charger-card {{
  animation: cardEntry 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}}

@keyframes availPulse {{
  0%, 100% {{ box-shadow: 0 0 0 0 {css_vars.get('--green', '#22c55e')}4d; }}
  50% {{ box-shadow: 0 0 12px 4px {css_vars.get('--green', '#22c55e')}26; }}
}}

.status-badge.available {{
  animation: availPulse 2s ease-in-out infinite;
}}

.btn {{
  transition: transform 0.15s ease, box-shadow 0.2s ease, opacity 0.15s ease;
}}

.btn-primary:hover {{
  box-shadow: 0 4px 20px {css_vars.get('--accent', '#00B0E4')}4d;
}}

@keyframes chargingGlow {{
  0%, 100% {{ box-shadow: 0 0 20px {css_vars.get('--accent', '#00B0E4')}14; }}
  50% {{ box-shadow: 0 0 40px {css_vars.get('--accent', '#00B0E4')}33; }}
}}

.charging-active {{
  animation: chargingGlow 2s ease-in-out infinite;
  border-color: var(--accent) !important;
}}

@keyframes charging-glow {{
  0%, 100% {{ filter: drop-shadow(0 0 8px {css_vars.get('--accent', '#00B0E4')}4d); }}
  50% {{ filter: drop-shadow(0 0 24px {css_vars.get('--accent', '#00B0E4')}b3) drop-shadow(0 0 48px {css_vars.get('--green', '#22c55e')}33); }}
}}

.power-value.charging {{
  animation: charging-glow 2s ease-in-out infinite;
}}

@keyframes otpSuccess {{
  0% {{ border-color: var(--border); }}
  50% {{ border-color: var(--green); box-shadow: 0 0 12px {css_vars.get('--green', '#22c55e')}4d; }}
  100% {{ border-color: var(--green); }}
}}

.otp-success {{
  animation: otpSuccess 0.6s ease-out forwards;
}}

@keyframes checkBounce {{
  0% {{ transform: scale(0); opacity: 0; }}
  50% {{ transform: scale(1.2); opacity: 1; }}
  100% {{ transform: scale(1); opacity: 1; }}
}}

.check-bounce {{
  animation: checkBounce 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
}}

@keyframes pinDrop {{
  0% {{ transform: translateY(-20px); opacity: 0; }}
  60% {{ transform: translateY(3px); opacity: 1; }}
  100% {{ transform: translateY(0); }}
}}

.leaflet-marker-icon {{
  animation: pinDrop 0.4s ease-out;
}}

@keyframes shimmer {{
  0% {{ background-position: -200% 0; }}
  100% {{ background-position: 200% 0; }}
}}

.skeleton {{
  background: linear-gradient(90deg, var(--bg2) 25%, var(--bg3) 50%, var(--bg2) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
  border-radius: 8px;
}}

@keyframes errorShake {{
  0%, 100% {{ transform: translateX(0); }}
  20%, 60% {{ transform: translateX(-6px); }}
  40%, 80% {{ transform: translateX(6px); }}
}}

.error-card {{
  animation: errorShake 0.4s ease-out;
}}

/* ── Leaflet z-index overrides ── */

.leaflet-top, .leaflet-bottom {{ z-index: 999 !important; }}
.leaflet-pane {{ z-index: 400 !important; }}
.leaflet-tile-pane {{ z-index: 200 !important; }}
.leaflet-overlay-pane {{ z-index: 400 !important; }}
.leaflet-marker-pane {{ z-index: 600 !important; }}
.leaflet-tooltip-pane {{ z-index: 650 !important; }}
.leaflet-popup-pane {{ z-index: 700 !important; }}

/* ── User dot ── */

.user-dot-outer {{
  width: 20px; height: 20px; border-radius: 50%;
  background: {css_vars.get('--accent', '#00B0E4')}4d;
  display: flex; align-items: center; justify-content: center;
  animation: userPulse 2s ease-in-out infinite;
}}

.user-dot-inner {{
  width: 10px; height: 10px; border-radius: 50%;
  background: var(--accent);
}}

@keyframes userPulse {{
  0%, 100% {{ transform: scale(1); }}
  50% {{ transform: scale(1.3); }}
}}

/* ── Scan ── */

@keyframes scanLine {{
  0%, 100% {{ top: 10%; }}
  50% {{ top: 90%; }}
}}

/* ── Pin marker ── */

.charger-marker-wrap {{ background: none !important; border: none !important; }}

.pin-pulse {{
  animation: pinPulse 2s ease-in-out infinite;
}}

@keyframes pinPulse {{
  0%, 100% {{ filter: drop-shadow(0 0 0px transparent); }}
  50% {{ filter: drop-shadow(0 0 8px {css_vars.get('--accent', '#00B0E4')}80); }}
}}
"""
    return css


# ── Main pipeline ─────────────────────────────────────────────────────────

def process_stitch_export(input_path: str, skin_name: str, output_dir: str):
    """Main pipeline: Stitch export → skin directory."""

    # Handle zip or directory
    if zipfile.is_zipfile(input_path):
        tmpdir = tempfile.mkdtemp()
        with zipfile.ZipFile(input_path, 'r') as z:
            z.extractall(tmpdir)
        source_dir = tmpdir
    else:
        source_dir = input_path
        tmpdir = None

    # Find all code.html files
    html_files = []
    for root, dirs, files in os.walk(source_dir):
        for f in files:
            if f == 'code.html':
                html_files.append(os.path.join(root, f))

    if not html_files:
        print(f"Error: No code.html files found in {input_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(html_files)} Stitch screen(s)")

    # Extract tokens from the first HTML (they should all be consistent)
    with open(html_files[0], 'r') as f:
        primary_html = f.read()

    config = extract_tailwind_config(primary_html)
    if not config:
        print("Error: Could not extract Tailwind config", file=sys.stderr)
        sys.exit(1)

    extend = config.get('theme', {}).get('extend', {})
    stitch_colors = extend.get('colors', {})
    fonts = extend.get('fontFamily', {})
    radii = extend.get('borderRadius', {})

    # Flatten font arrays (Stitch stores them as ["FontName"])
    for k, v in fonts.items():
        if isinstance(v, list):
            fonts[k] = v[0] if v else 'system-ui'

    print(f"Extracted {len(stitch_colors)} color tokens, {len(fonts)} font families")

    # Map to CSS vars
    css_vars = map_colors(stitch_colors)
    mode = determine_mode(stitch_colors)
    print(f"Detected mode: {mode}")

    # Collect custom CSS from all HTML files
    all_custom_css = []
    for hf in html_files:
        with open(hf, 'r') as f:
            css = extract_custom_css(f.read())
            if css:
                all_custom_css.append(f"/* From {os.path.basename(os.path.dirname(hf))} */\n{css}")

    custom_css = '\n\n'.join(all_custom_css)

    # Generate outputs
    skin_json = generate_skin_json(skin_name, stitch_colors, fonts, mode)
    style_css = generate_style_css(css_vars, stitch_colors, fonts, radii, mode, custom_css)

    # Write skin directory
    skin_dir = os.path.join(output_dir, skin_name.lower().replace(' ', '-'))
    static_dir = os.path.join(skin_dir, 'static')
    os.makedirs(static_dir, exist_ok=True)

    with open(os.path.join(skin_dir, 'skin.json'), 'w') as f:
        json.dump(skin_json, f, indent=2)
        f.write('\n')

    with open(os.path.join(static_dir, 'style.css'), 'w') as f:
        f.write(style_css)

    # Find and copy DESIGN.md if present
    for root, dirs, files in os.walk(source_dir):
        for fn in files:
            if fn == 'DESIGN.md':
                import shutil
                shutil.copy2(os.path.join(root, fn), os.path.join(skin_dir, 'DESIGN.md'))
                break

    # Copy screen PNGs as previews
    previews_dir = os.path.join(skin_dir, 'previews')
    os.makedirs(previews_dir, exist_ok=True)
    for hf in html_files:
        screen_dir = os.path.dirname(hf)
        screen_name = os.path.basename(screen_dir)
        png = os.path.join(screen_dir, 'screen.png')
        if os.path.exists(png):
            import shutil
            shutil.copy2(png, os.path.join(previews_dir, f'{screen_name}.png'))

    print(f"\n✅ Skin '{skin_name}' created at {skin_dir}/")
    print(f"   skin.json: {os.path.join(skin_dir, 'skin.json')}")
    print(f"   style.css: {os.path.join(static_dir, 'style.css')} ({len(style_css)} bytes)")
    print(f"   previews:  {len(os.listdir(previews_dir))} screen(s)")

    if tmpdir:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(
        description='Convert a Google Stitch export to an OpenCPO charge app skin'
    )
    parser.add_argument('input', help='Path to Stitch zip or unpacked directory')
    parser.add_argument('name', help='Skin name (e.g. "voltage-backstage")')
    parser.add_argument('--output-dir', '-o', default='skins/',
                       help='Output directory for skins (default: skins/)')
    args = parser.parse_args()

    process_stitch_export(args.input, args.name, args.output_dir)


if __name__ == '__main__':
    main()
