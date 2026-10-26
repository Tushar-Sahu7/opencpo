# Skins

Skins control the visual appearance of the charge app without modifying any engine code. Swap the `SKIN` environment variable and the entire app looks different.

## How It Works

The skin system uses a simple file-override pattern:

1. Templates: `skins/{SKIN}/templates/` overrides `templates/`
2. Static files: `skins/{SKIN}/static/` served at `/skin/` URL prefix
3. Base static: always available at `/static/` (JS, HTMX, etc.)

If a skin doesn't override a template, the base engine template is used.

## Creating a Skin

### 1. Create the directory

```
skins/my-brand/
├── skin.json
├── static/
│   └── style.css
└── templates/           # (optional — only for template overrides)
```

### 2. Define `skin.json`

```json
{
  "name": "My Brand",
  "version": "1.0",
  "colors": {
    "primary": "#FF6600",
    "secondary": "#00CC44",
    "background": "#1a1a2e",
    "card": "#16213e",
    "border": "#0f3460"
  },
  "logo": "logo.svg",
  "favicon": "favicon.svg"
}
```

The `skin.json` metadata is read by templates to set theme colors and branding.

### 3. Create `static/style.css`

This is your full CSS. The base template loads it from `/skin/style.css`:

```css
/* skins/my-brand/static/style.css */

:root {
  --color-primary: #FF6600;
  --color-secondary: #00CC44;
  --color-bg: #1a1a2e;
  --color-card: #16213e;
  --color-border: #0f3460;
  --color-text: #e2e8f0;
  --color-text-muted: #94a3b8;
  --border-radius: 12px;
  --font-family: 'Inter', system-ui, sans-serif;
}

body {
  background: var(--color-bg);
  color: var(--color-text);
  font-family: var(--font-family);
  margin: 0;
  padding: 0;
}

.card {
  background: var(--color-card);
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius);
  padding: 1.5rem;
}

.btn-primary {
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: var(--border-radius);
  padding: 0.75rem 1.5rem;
  font-size: 1rem;
  cursor: pointer;
}

.btn-primary:hover {
  filter: brightness(1.1);
}
```

### 4. Activate

```env
SKIN=my-brand
```

### 5. (Optional) Override templates

To customize the charge screen layout:

```
skins/my-brand/templates/
└── charge.html    ← overrides templates/charge.html
```

Your overridden template has access to all the same variables as the base template (`flags`, `t`, `lang`, `account`, etc.).

## CSS Variables

The recommended approach is to define CSS custom properties in `:root` and use them throughout. This makes it easy for other skins to override just the colors without duplicating all the CSS.

### Standard variables

```css
:root {
  /* Colors */
  --color-primary: #2563eb;
  --color-secondary: #16a34a;
  --color-bg: #0f172a;
  --color-card: #1e293b;
  --color-border: #334155;
  --color-text: #e2e8f0;
  --color-text-muted: #94a3b8;
  --color-success: #22c55e;
  --color-warning: #f59e0b;
  --color-error: #ef4444;

  /* Layout */
  --border-radius: 12px;
  --spacing: 1rem;
  --max-width: 480px;       /* Mobile-first: max width of content */

  /* Typography */
  --font-family: system-ui, sans-serif;
  --font-size-base: 1rem;
  --font-size-lg: 1.25rem;
  --font-size-xl: 1.5rem;
  --font-size-sm: 0.875rem;
}
```

## Static Asset URLs

In templates, reference skin and base assets:

```html
<!-- Skin CSS (overrides base) -->
<link rel="stylesheet" href="/skin/style.css">

<!-- Base JS (always available) -->
<script src="/static/htmx.min.js"></script>
<script src="/static/home.js"></script>

<!-- Skin-specific assets -->
<img src="/skin/logo.svg" alt="Logo">

<!-- Base assets (fallback) -->
<img src="/static/logo.svg" alt="Logo">
```

## Default Skin

The `default` skin ships with the repository and provides a clean, functional dark theme:

```json
{
  "name": "Default",
  "version": "1.0",
  "colors": {
    "primary": "#2563eb",
    "secondary": "#16a34a",
    "background": "#0f172a",
    "card": "#1e293b",
    "border": "#334155"
  }
}
```

This is a fully usable starting point. Fork it to create your own skin.

## Tips

- **Mobile first** — the app is designed for phone browsers. Keep `max-width: 480px` for content.
- **Dark mode** — both built-in skins use dark backgrounds. If you want light mode, override `--color-bg`, `--color-card`, and `--color-text`.
- **Logo format** — SVG recommended for crisp rendering on all screen sizes. Include both a light and dark version if your logo needs it.
- **PWA icons** — override `static/icon-192.png` and `static/icon-512.png` for the PWA install icon.
- **Manifest** — override `static/manifest.json` for the PWA name, theme color, and icons.
