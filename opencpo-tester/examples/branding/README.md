# Custom Branding

The OCPP Compliance Tester supports custom branding in generated PDF and HTML reports.

## Configuration

Add a `branding` section to your `config.yaml`:

```yaml
branding:
  company: "Your Company Name"
  logo_path: null            # path to SVG logo file, null = no logo
  logo_color_path: null      # optional: separate logo for light backgrounds
  primary_color: "#1e3a5f"   # header/table header color
  accent_color: "#2563eb"    # accent/highlight color
  green_color: "#16a34a"     # pass/success color
```

## Logo Requirements

- **Format:** SVG (recommended for crispness at any size)
- **Dimensions:** Any — the reports scale it to fit (target: ~320×56px aspect ratio)
- **For dark headers:** Use a white/light version of your logo
- **For light footers:** Use a color/dark version

If `logo_path` is `null`, the reports render without a logo (generic look).

## Examples

### `example/`
A generic example to show how branding works — replace the logos and colors with your own.

- `logo-white.svg` — white logo for dark header backgrounds
- `logo-color.svg` — color/navy logo for light backgrounds
- `config.yaml` — ready-to-use branding config snippet

## How It Works

When you run the tester, `config.yaml` is loaded and `branding.*` values are passed
through to the report generator. The HTML and PDF generators read these values
instead of any hardcoded defaults.

The logo SVG file is read at report-generation time, base64-encoded, and embedded
inline in the output — so the report is fully standalone with no external dependencies.
