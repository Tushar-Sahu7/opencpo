# Reports

The compliance tester generates reports in PDF and/or HTML format after each test run.

## Report Formats

| Format | When to use |
|---|---|
| `pdf` | Formal submission to certifying body or customer |
| `html` | Web review, email attachment, CI artifacts |
| `both` | Generate both (default) |
| `none` | Suppress report generation (e.g., during development) |

Set the format in `config.yaml`:

```yaml
report:
  format: "both"    # pdf, html, both, none
  output: null      # null = auto-generate filename like report_20240115_143022
```

If `output` is set:
- PDF → `{output}.pdf`
- HTML → `{output}.html`

If `output` is null, files are written to the `output/` directory with a timestamp in the name.

## Report Contents

Both PDF and HTML reports include:

1. **Cover page** — company name, logo, charger identity (vendor, model, firmware), test date
2. **Executive summary** — pass/fail counts, compliance grade, overall pass rate
3. **Test results table** — all tests with status, severity, spec reference, message
4. **Failure details** — for each failing test: what was expected, what happened, fix recommendation
5. **Message exchanges** — raw OCPP messages for each test (useful for debugging)
6. **Grade** — letter grade (A/B/C/D/F) with label

### Grading

| Pass rate | Grade | Label |
|---|---|---|
| ≥ 95% | A | Fully Compliant |
| ≥ 90% | B | Mostly Compliant |
| ≥ 75% | C | Partially Compliant |
| ≥ 65% | D | Significant Issues |
| < 65% | F | Not Compliant |

Skipped tests are excluded from the pass rate calculation.

## Customization

All branding is configured in `config.yaml` under the `branding` section:

```yaml
branding:
  company: "Your Company Name"
  logo_path: "/path/to/logo.svg"
  logo_color_path: null
  primary_color: "#1e3a5f"
  accent_color: "#2563eb"
  green_color: "#16a34a"
```

- `company` — appears in the report header and footer
- `logo_path` — SVG logo displayed in the report header. PNG also works for PDF; SVG is preferred for HTML
- `logo_color_path` — optional separate logo for light backgrounds (HTML reports may need this if the default logo is white/light)
- `primary_color` — header backgrounds and table headers
- `accent_color` — hyperlinks and highlights
- `green_color` — pass indicators

Colors must be hex codes (`#RRGGBB`).

## JSON Output

In addition to PDF and HTML, a machine-readable JSON summary is always written alongside the reports:

```json
{
  "generated_at": "2024-01-15T14:30:22Z",
  "charger": {
    "vendor": "ACME",
    "model": "FastCharge-50",
    "firmware": "FW2.4.1"
  },
  "summary": {
    "total": 47,
    "passed": 42,
    "failed": 3,
    "skipped": 2,
    "errors": 0,
    "pass_rate": 93.3,
    "grade": "B"
  },
  "results": [
    {
      "test_name": "boot_notification_required_fields",
      "category": "boot",
      "status": "PASS",
      "severity": "CRITICAL",
      "message": "All required fields present",
      "spec_ref": "OCPP 1.6 §4.1",
      "duration_s": 0.12,
      "exchanges": [...]
    }
  ]
}
```

Use the JSON for integration with CI/CD pipelines:

```bash
python main.py --config config.yaml
# Check exit code: 0 = all critical tests passed, 1 = critical failures
echo $?
```

Exit codes:
- `0` — All CRITICAL tests passed (WARNING/INFO failures allowed)
- `1` — One or more CRITICAL tests failed
- `2` — Could not connect to charger (timeout)
