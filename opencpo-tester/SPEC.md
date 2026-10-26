# OCPP Compliance Tester — Spec

## Purpose
QA tool that acts as a CSMS, connects to a charger via WebSocket, runs the OCPP test suite, and generates a deviation report to send to the manufacturer.

## How It Works
1. Start the tester → opens a WebSocket server (like a CSMS)
2. Charger connects to it (same way it connects to our OCPP Core)
3. Tester runs test scenarios against the charger
4. Each test validates the charger's messages against the OCPP spec
5. Generates a PDF/HTML report: PASS/FAIL per test, exact deviations

## OCPP Versions
- **1.6j** — current generation chargers
- **2.0.1** — future chargers, already supported in our OCPP Core
- Both versions share the same test concepts but different message schemas

## Test Categories

### 1. Connection & Boot (mandatory)
- [ ] Charger sends valid BootNotification on connect
- [ ] BootNotification contains required fields (vendor, model, serial, firmware)
- [ ] Charger respects HeartbeatInterval from BootNotification.conf
- [ ] Charger sends Heartbeat at configured interval (±10% tolerance)
- [ ] Charger reconnects after WebSocket close
- [ ] Charger handles BootNotification Rejected/Pending status

### 2. Status Reporting
- [ ] StatusNotification sent for each connector on boot
- [ ] StatusNotification on connector state change
- [ ] Valid status values (Available, Preparing, Charging, SuspendedEV, SuspendedEVSE, Finishing, Faulted)
- [ ] Valid errorCode values
- [ ] Connector IDs are consistent (0 = charger, 1+ = connectors)

### 3. Authorization
- [ ] Authorize request with valid idTag → Accepted
- [ ] Authorize request with unknown idTag → handle response correctly
- [ ] Authorize request with blocked idTag → handle response correctly
- [ ] Local authorization list support (if claimed in BootNotification)

### 4. Transactions (StartTransaction / StopTransaction)
- [ ] StartTransaction sent after authorization
- [ ] StartTransaction contains: connectorId, idTag, meterStart, timestamp
- [ ] Charger uses transactionId from StartTransaction.conf
- [ ] StopTransaction sent on session end
- [ ] StopTransaction contains: transactionId, meterStop, timestamp, reason
- [ ] StopTransaction reasons are valid (EVDisconnected, Local, Remote, etc.)
- [ ] meterStop ≥ meterStart

### 5. Meter Values
- [ ] MeterValues sent during charging
- [ ] MeterValues contain Energy.Active.Import.Register (Wh)
- [ ] Timestamps are valid ISO 8601
- [ ] Measurand values have correct units
- [ ] MeterValues interval matches configured SampledDataInterval
- [ ] MeterValues at start/stop of transaction (if configured)

### 6. Remote Control
- [ ] RemoteStartTransaction → charger starts (or rejects with reason)
- [ ] RemoteStopTransaction → charger stops active session
- [ ] Reset (Soft) → charger reboots and reconnects
- [ ] Reset (Hard) → charger reboots and reconnects
- [ ] ChangeConfiguration → charger accepts/rejects with correct status
- [ ] GetConfiguration → returns current config values
- [ ] UnlockConnector → charger responds correctly

### 7. Smart Charging (if supported)
- [ ] SetChargingProfile → accepted
- [ ] ClearChargingProfile → accepted
- [ ] GetCompositeSchedule → returns valid schedule
- [ ] Charger respects power limits from charging profile
- [ ] TxDefaultProfile vs TxProfile precedence

### 8. Firmware & Diagnostics (if supported)
- [ ] UpdateFirmware → charger downloads and installs
- [ ] FirmwareStatusNotification sent during update
- [ ] GetDiagnostics → charger uploads log
- [ ] DiagnosticsStatusNotification sent

### 9. Protocol Compliance
- [ ] All messages have valid JSON structure
- [ ] MessageId is unique per request
- [ ] Correct OCPP message types (2=Call, 3=CallResult, 4=CallError)
- [ ] Charger handles unknown messages gracefully (CallError, not crash)
- [ ] Charger handles malformed responses gracefully
- [ ] WebSocket ping/pong support
- [ ] Correct subprotocol negotiation (ocpp1.6, ocpp2.0.1)

## Report Format

### PDF Report
- **Header:** Operator logo (configurable), date, charger details (vendor, model, serial, firmware)
- **Summary:** X/Y tests passed, overall compliance score
- **Per-category breakdown:** category name, pass/fail count, severity
- **Deviation details:** For each FAIL:
  - Test name
  - What the spec requires
  - What the charger actually did
  - Raw message exchange (request → response)
  - Severity: CRITICAL / WARNING / INFO
  - OCPP spec reference (section number)
- **Recommendations:** What the manufacturer should fix

### Severity Levels
- **CRITICAL:** Breaks interoperability (wrong message format, missing required fields)
- **WARNING:** Deviates from spec but works in practice (wrong enum value, timing off)
- **INFO:** Best practice recommendation (optional fields missing, suboptimal behavior)

## Architecture
```
opencpo-tester/
├── main.py                 # CLI entry point
├── server.py               # WebSocket CSMS server
├── runner.py               # Test runner / orchestrator
├── tests/
│   ├── __init__.py
│   ├── base.py             # Test base class
│   ├── boot.py             # Connection & boot tests
│   ├── status.py           # StatusNotification tests
│   ├── auth.py             # Authorization tests
│   ├── transactions.py     # Start/Stop transaction tests
│   ├── meter_values.py     # MeterValues tests
│   ├── remote_control.py   # Remote commands tests
│   ├── smart_charging.py   # Charging profiles tests
│   ├── firmware.py         # Firmware & diagnostics tests
│   └── protocol.py         # Protocol compliance tests
├── report/
│   ├── __init__.py
│   ├── generator.py        # Report generator
│   ├── pdf.py              # PDF output
│   ├── html.py             # HTML output
│   └── template.html       # Report template
├── ocpp_messages/
│   ├── __init__.py
│   ├── v16.py              # OCPP 1.6 message definitions
│   └── v201.py             # OCPP 2.0.1 message definitions
├── config.yaml             # Test configuration
└── requirements.txt
```

## CLI Usage
```bash
# Start tester on port 9300, wait for charger to connect
ocpp-tester --port 9300 --version 1.6

# Run specific test categories
ocpp-tester --port 9300 --tests boot,status,transactions

# Generate report
ocpp-tester --port 9300 --report pdf --output report.pdf

# Full compliance run
ocpp-tester --port 9300 --full --report pdf --output example-compliance-report.pdf
```

## How a Test Run Works
1. Tester starts WebSocket server
2. User points charger at ws://localhost:9300/ocpp/{charger-id}
3. Charger connects, sends BootNotification
4. Tester captures BootNotification, validates, responds
5. Tester waits for StatusNotification(s)
6. Tester runs automated scenarios:
   - Sends RemoteStartTransaction → waits for StartTransaction
   - Monitors MeterValues during charging
   - Sends RemoteStopTransaction → waits for StopTransaction
   - Sends ChangeConfiguration → checks response
   - etc.
7. Some tests require physical interaction (plug in cable, tap RFID)
   → Tester prompts user in CLI: "Please plug in cable to connector 1, then press Enter"
8. After all tests: generate report

## Config
```yaml
server:
  port: 9300
  version: "1.6"  # or "2.0.1"

charger:
  expected_vendor: "charger vendor"
  expected_model: "your-model"

timing:
  heartbeat_interval: 30
  meter_interval: 10
  boot_timeout: 60
  test_timeout: 120

tests:
  skip: []  # skip specific tests
  only: []  # run only these (empty = all)
```
