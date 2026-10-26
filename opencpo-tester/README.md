# OCPP Compliance Tester

An automated compliance testing tool for EV chargers. It acts as a CSMS (Central System), connects to your charger over WebSocket, runs a comprehensive test suite against the OCPP 1.6 and 2.0.1 specifications, and generates professional PDF, HTML, and JSON reports with per-test results, message exchanges, spec references, and fix recommendations.

---

## Quick Start

### Install

```bash
pip install ocpp-compliance-tester
```

Or run directly from source:

```bash
git clone https://github.com/opencpo/opencpo-tester
cd ocpp-compliance-tester
pip install -r requirements.txt
```

### Run against a charger

```bash
# Listen on port 9300, auto-detect OCPP version, generate PDF + HTML report
ocpp-tester --port 9300

# Force OCPP 1.6, run specific test categories
ocpp-tester --port 9300 --version 1.6 --tests boot,status,transactions

# Skip interactive tests (no physical cable plug prompts), PDF only
ocpp-tester --port 9300 --no-interactive --report pdf

# Full suite including firmware/diagnostics (requires physical intervention)
ocpp-tester --port 9300 --full --report both --output report-charger-x.pdf
```

Point your charger at `ws://<your-machine-ip>:9300/ocpp/<charger-id>`. The tester starts listening and begins testing immediately upon connection.

---

## Test Categories

| Category | Spec | What's tested |
|---|---|---|
| **Connection & Boot** | OCPP 1.6 §5.2, §5.5 | BootNotification payload, heartbeat timing |
| **Status Notifications** | OCPP 1.6 §5.18 | Connector status enums, timestamp format |
| **Protocol Compliance** | OCPP 1.6 §4 | Message framing, uniqueId, error handling |
| **Authorization** | OCPP 1.6 §5.1 | Authorize request/response, idTag format |
| **Transaction Management** | OCPP 1.6 §5.16, §5.17 | StartTransaction, StopTransaction, meter consistency |
| **Meter Values** | OCPP 1.6 §5.11 | Measurands, monotonic timestamps, parseable values |
| **Remote Control** | OCPP 1.6 §5.4–§5.20 | Reset, ChangeConfiguration, GetConfiguration, TriggerMessage |
| **Smart Charging** | OCPP 1.6 §5.3, §5.8, §5.10 | SetChargingProfile, ClearChargingProfile, GetCompositeSchedule |
| **Firmware & Diagnostics** | OCPP 1.6 §5.21, §5.22 | UpdateFirmware, GetDiagnostics status flows |

---

## Report Output

Each test run generates three files:

- **`report-Vendor-Model-YYYY-MM-DD.pdf`** — printable professional report with cover page, grade (A+–F), per-category results, deviation details with raw message exchanges, and manufacturer fix recommendations
- **`report-Vendor-Model-YYYY-MM-DD.html`** — standalone browser report (no external dependencies)
- **`report-Vendor-Model-YYYY-MM-DD.json`** — machine-readable results for dashboard integration

---

## Configuration

Copy `config.yaml.example` to `config.yaml` and adjust:

```bash
cp config.yaml.example config.yaml
```

Key settings:

```yaml
server:
  port: 9300

tests:
  timeout: 120
  interactive: true   # set false to skip physical-action tests
  skip: []            # e.g. [firmware, smart_charging]

branding:
  company: "Your Company"
  logo_path: null     # path to SVG logo, null = no logo

rfid:
  valid_tag: "TESTCARD01"
  invalid_tag: "DEADBEEF99"
```

See [`config.yaml.example`](config.yaml.example) for all options with documentation.

---

## Custom Branding

Reports support custom branding — logo, company name, and colors — configurable via `config.yaml` or the `--company` CLI flag.

```yaml
branding:
  company: "Acme EV Solutions"
  logo_path: "path/to/logo-white.svg"      # for dark header
  logo_color_path: "path/to/logo-color.svg" # for light footer (optional)
  primary_color: "#1e3a5f"
  accent_color: "#2563eb"
  green_color: "#16a34a"
```

See [`examples/branding/README.md`](examples/branding/README.md) for logo requirements and the included Stroomlijnen branding example.

---

## CLI Reference

```
usage: ocpp-tester [options]

options:
  --port PORT           WebSocket server port (default: 9300)
  --host HOST           Bind address (default: 0.0.0.0)
  --version {1.6,2.0.1,auto}
                        OCPP version (default: auto-detect)
  --tests TESTS         Comma-separated categories to run
  --skip SKIP           Comma-separated categories to skip
  --full                Include firmware/diagnostics tests
  --report {pdf,html,both,none}
                        Report format (default: both)
  --output OUTPUT       Output file base name
  --timeout TIMEOUT     Per-test timeout in seconds (default: 120)
  --no-interactive      Disable physical interaction prompts
  --company COMPANY     Company name for reports
  --config CONFIG       Path to config.yaml
  --tls-cert CERT       TLS certificate for WSS
  --tls-key KEY         TLS private key for WSS
  -v, --verbose         Verbose logging
```

---

## Contributing

Pull requests welcome. Please:

1. Keep all test logic intact — tests are in `tests/v16/` and `tests/v201/`
2. New tests should subclass `tests.base.BaseTest` and use the existing result/severity system
3. Add/update `TEST_CRITERIA` in `report/generator.py` when adding test categories
4. Run `python -m pytest` before submitting

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).
