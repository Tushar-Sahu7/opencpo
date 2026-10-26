# Configuration Reference

All configuration lives in `config.yaml`. Copy `config.yaml.example` to `config.yaml` and edit.

## Full Reference

```yaml
server:
  port: 9300          # Port the compliance tester listens on
  version: "auto"     # OCPP version: "auto" (detect), "1.6", or "2.0.1"
  tls: false          # Enable TLS
  tls_cert: null      # Path to TLS certificate file
  tls_key: null       # Path to TLS private key file

charger:
  expected_vendor: null    # If set, fail if BootNotification.vendor doesn't match
  expected_model: null     # If set, fail if BootNotification.model doesn't match
  num_connectors: 1        # Expected number of physical connectors

timing:
  heartbeat_interval: 30   # Heartbeat interval to send in BootNotification response (seconds)
  meter_interval: 10       # Expected meter value sample interval (seconds)
  boot_timeout: 60         # Seconds to wait for charger to connect after starting
  test_timeout: 120        # Per-test timeout (seconds) — increase for slow chargers
  transaction_start_max: 5 # Max seconds allowed between auth and StartTransaction

tests:
  skip: []    # Categories to skip, e.g. [firmware, smart_charging]
  only: []    # Run only these categories (empty = all)
  full: false # Include firmware/diagnostics tests (adds significant time)
  interactive: true  # Enable prompts for tests requiring physical interaction

branding:
  company: "OCPP Compliance Tester"   # Company name on reports
  logo_path: null                     # Path to SVG logo (null = no logo)
  logo_color_path: null               # Optional: separate logo for light backgrounds
  primary_color: "#1e3a5f"            # Header color (hex)
  accent_color: "#2563eb"             # Accent/link color (hex)
  green_color: "#16a34a"              # Pass/success indicator color (hex)

report:
  format: "both"   # Output format: "pdf", "html", "both", or "none"
  output: null     # Output filename base (null = auto-generated from timestamp)

rfid:
  valid_tag: "TESTCARD01"    # An RFID tag that your charger accepts
  invalid_tag: "INVALID99"   # A tag your charger should reject (unknown/not in DB)
  blocked_tag: null          # A specifically blocked tag (optional)
```

## Quickstart Config

Minimum config to get started:

```yaml
server:
  port: 9300
  version: auto

timing:
  boot_timeout: 60

rfid:
  valid_tag: "YOUR-RFID-TAG"
```

## Running

```bash
# Point your charger at ws://your-host:9300/ocpp/{id}
python main.py --config config.yaml

# Run only specific categories
python main.py --categories boot status transactions

# Skip firmware tests (slow)
python main.py --skip firmware

# Non-interactive (CI/CD)
python main.py --no-interactive
```

## Category Reference

| Category | What it tests |
|---|---|
| `boot` | BootNotification fields, timing, reconnect behavior |
| `status` | StatusNotification connector states and transitions |
| `auth` | Authorize — valid, invalid, blocked, expired tokens |
| `transactions` | StartTransaction, StopTransaction, energy accounting |
| `meter_values` | MeterValues measurands, units, intervals |
| `remote_control` | RemoteStartTransaction, RemoteStopTransaction |
| `smart_charging` | SetChargingProfile, ClearChargingProfile |
| `firmware` | GetDiagnostics, UpdateFirmware (requires `full: true`) |
| `protocol` | Message format, error responses, unknown actions |
