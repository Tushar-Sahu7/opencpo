# Test Reference

Complete list of all tests by category. Tests run in the order shown.

**Severity levels:**
- `CRITICAL` — Fundamental OCPP requirement; failure means the charger cannot be used
- `WARNING` — Important compliance issue; may cause interoperability problems
- `INFO` — Minor deviation from spec; unlikely to cause problems in practice

---

## Boot (`boot`)

Tests that verify BootNotification behavior and charger startup sequence.

| Test Name | Checks | Spec Ref | Pass Criteria | Severity |
|---|---|---|---|---|
| `boot_notification_required_fields` | `chargePointVendor` and `chargePointModel` present | OCPP 1.6 §4.1 | Both fields non-empty | CRITICAL |
| `boot_notification_field_lengths` | Field values within CiString length limits | OCPP 1.6 §4.1 | All fields ≤ max length | CRITICAL |
| `boot_response_accepted` | Server response contains `status: Accepted` | OCPP 1.6 §4.1 | Charger proceeds after Accepted | CRITICAL |
| `heartbeat_sent` | Charger sends Heartbeat after BootNotification | OCPP 1.6 §4.4 | Heartbeat received within 2× heartbeat interval | WARNING |
| `heartbeat_timing` | Heartbeat sent at approximately the configured interval | OCPP 1.6 §4.4 | Within 20% of configured interval | WARNING |
| `status_notification_after_boot` | Charger sends StatusNotification for each connector | OCPP 1.6 §4.7 | StatusNotification received for all connectors | WARNING |
| `boot_notification_sends_serial` | Serial number present in BootNotification | OCPP 1.6 §4.1 | `chargePointSerialNumber` not empty | INFO |
| `boot_notification_sends_firmware` | Firmware version present | OCPP 1.6 §4.1 | `firmwareVersion` not empty | INFO |

---

## Status (`status`)

Tests that verify connector status transitions and reporting.

| Test Name | Checks | Spec Ref | Pass Criteria | Severity |
|---|---|---|---|---|
| `status_available_on_boot` | Connectors report Available when idle | OCPP 1.6 §4.7 | At least one connector shows Available | CRITICAL |
| `status_notification_connector_zero` | Connector 0 status report (optional) | OCPP 1.6 §4.7 | Either present or absent consistently | INFO |
| `status_valid_values` | Status values are valid OCPP enum values | OCPP 1.6 §4.7 | All statuses from spec enum | CRITICAL |
| `error_code_no_error` | Idle connectors report `NoError` | OCPP 1.6 §4.7 | `errorCode: NoError` when no fault | WARNING |

---

## Authorization (`auth`)

Tests that verify token authorization behavior.

| Test Name | Checks | Spec Ref | Pass Criteria | Severity | Interactive |
|---|---|---|---|---|---|
| `authorize_valid_idtag` | Valid RFID tag returns `Accepted` | OCPP 1.6 §4.2 | `idTagInfo.status: Accepted` | CRITICAL | Yes |
| `authorize_invalid_idtag` | Unknown RFID tag returns `Invalid` | OCPP 1.6 §4.2 | `idTagInfo.status: Invalid` | CRITICAL | Yes |
| `authorize_contains_idtag_info` | Response contains `idTagInfo` object | OCPP 1.6 §4.2 | Object present with `status` field | CRITICAL | No |
| `authorize_response_time` | Authorization response within 5 seconds | OCPP 1.6 §4.2 | Response < 5s | WARNING | No |

---

## Transactions (`transactions`)

Tests that verify charging session lifecycle.

| Test Name | Checks | Spec Ref | Pass Criteria | Severity |
|---|---|---|---|---|
| `start_transaction_required_fields` | `connectorId`, `idTag`, `meterStart`, `timestamp` all present | OCPP 1.6 §4.5 | All required fields non-null | CRITICAL |
| `start_transaction_response` | Response contains `transactionId` and `idTagInfo` | OCPP 1.6 §4.5 | `transactionId` is an integer | CRITICAL |
| `stop_transaction_required_fields` | `transactionId`, `meterStop`, `timestamp` all present | OCPP 1.6 §4.6 | All required fields present | CRITICAL |
| `stop_transaction_meter_stop_ge_start` | `meterStop ≥ meterStart` | OCPP 1.6 §4.6 | Meter did not go backwards | CRITICAL |
| `stop_transaction_reason` | `reason` field uses valid enum value | OCPP 1.6 §4.6 | Value from spec enum or absent | WARNING |
| `transaction_id_unique` | Each session gets a unique transaction ID | OCPP 1.6 §4.5 | No duplicate transaction IDs | CRITICAL |
| `start_stop_timing` | StopTransaction references correct transaction | OCPP 1.6 §4.6 | `transactionId` matches StartTransaction response | CRITICAL |
| `remote_start_transaction` | RemoteStartTransaction triggers a session | OCPP 1.6 §5.11 | StartTransaction received within `timing.transaction_start_max` | CRITICAL |
| `remote_stop_transaction` | RemoteStopTransaction stops an active session | OCPP 1.6 §5.12 | StopTransaction received within timeout | CRITICAL |

---

## Meter Values (`meter_values`)

Tests that verify energy and power measurement reporting.

| Test Name | Checks | Spec Ref | Pass Criteria | Severity |
|---|---|---|---|---|
| `meter_values_sent` | MeterValues sent during active session | OCPP 1.6 §4.8 | At least one MeterValues received | CRITICAL |
| `meter_values_energy_import` | `Energy.Active.Import.Register` present | OCPP 1.6 §4.8 | Measurand present in sampled values | CRITICAL |
| `meter_values_energy_unit` | Energy measurand uses `Wh` or `kWh` | OCPP 1.6 §4.8 | Unit is `Wh` or `kWh` | CRITICAL |
| `meter_values_energy_increasing` | Energy register value monotonically increases | OCPP 1.6 §4.8 | Each sample ≥ previous | CRITICAL |
| `meter_values_interval` | Sample interval close to configured value | OCPP 1.6 §4.8 | Within 50% of expected interval | WARNING |
| `meter_values_has_transaction_id` | `transactionId` included in MeterValues | OCPP 1.6 §4.8 | Field present | WARNING |
| `meter_values_voltage_range` | Voltage readings in plausible range | — | 100–500V | WARNING |
| `meter_values_current_range` | Current readings in plausible range | — | 0–500A | WARNING |
| `meter_values_power_range` | Power readings in plausible range | — | 0–350000W | WARNING |

---

## Remote Control (`remote_control`)

| Test Name | Checks | Spec Ref | Pass Criteria | Severity |
|---|---|---|---|---|
| `get_configuration` | GetConfiguration returns configuration keys | OCPP 1.6 §5.5 | At least one key returned | WARNING |
| `change_configuration` | ChangeConfiguration updates a key | OCPP 1.6 §5.4 | Response `Accepted` or `RebootRequired` | WARNING |
| `trigger_message_heartbeat` | TriggerMessage(Heartbeat) causes a Heartbeat | OCPP 1.6 §5.14 | Heartbeat received after TriggerMessage | WARNING |
| `trigger_message_status` | TriggerMessage(StatusNotification) works | OCPP 1.6 §5.14 | StatusNotification received | WARNING |
| `unlock_connector` | UnlockConnector returns valid status | OCPP 1.6 §5.16 | Response is Unlocked or NotSupported | INFO |
| `change_availability` | ChangeAvailability changes connector state | OCPP 1.6 §5.3 | StatusNotification shows Unavailable | WARNING |
| `reset_soft` | Reset(Soft) causes BootNotification | OCPP 1.6 §5.10 | BootNotification received within 120s | WARNING |

---

## Smart Charging (`smart_charging`)

| Test Name | Checks | Spec Ref | Pass Criteria | Severity |
|---|---|---|---|---|
| `set_charging_profile_accepted` | SetChargingProfile returns Accepted | OCPP 1.6 §7.3 | Status: Accepted | WARNING |
| `charging_profile_applied` | Power limited by profile during charging | OCPP 1.6 §7.3 | MeterValues show power ≤ limit | WARNING |
| `clear_charging_profile` | ClearChargingProfile removes limits | OCPP 1.6 §7.4 | Power returns to normal after clear | INFO |
| `get_composite_schedule` | GetCompositeSchedule returns a schedule | OCPP 1.6 §7.2 | Valid schedule returned | INFO |

---

## Protocol (`protocol`)

Tests that verify OCPP-J message format compliance.

| Test Name | Checks | Spec Ref | Pass Criteria | Severity |
|---|---|---|---|---|
| `message_format_call` | CALL messages are valid JSON arrays `[2, id, action, payload]` | OCPP-J §2.2 | Correct array structure | CRITICAL |
| `message_format_callresult` | CALL_RESULT format `[3, id, payload]` | OCPP-J §2.2 | Correct structure | CRITICAL |
| `unique_id_per_message` | Each CALL has a unique ID | OCPP-J §2.2 | No duplicate IDs per connection | CRITICAL |
| `unique_id_in_response` | CALL_RESULT echoes same ID as CALL | OCPP-J §2.2 | Response ID matches request | CRITICAL |
| `unknown_action_error` | Unknown actions get CALL_ERROR response | OCPP 1.6 §4 | Error with `NotImplemented` or `NotSupported` | WARNING |
| `call_error_format` | CALL_ERROR has correct format `[4, id, code, desc, details]` | OCPP-J §2.2 | Five-element array | CRITICAL |
| `json_well_formed` | All messages are valid JSON | — | No JSON parse errors | CRITICAL |
| `payload_is_object` | CALL payloads are JSON objects, not arrays or primitives | OCPP-J §2.2 | `{}` type payload | CRITICAL |

---

## Firmware (`firmware`)

Only run with `full: true` in config. These tests trigger real charger behavior that takes significant time.

| Test Name | Checks | Spec Ref | Pass Criteria | Severity |
|---|---|---|---|---|
| `get_diagnostics` | GetDiagnostics triggers a DiagnosticsStatusNotification | OCPP 1.6 §5.6 | Status notification received | INFO |
| `firmware_update_status` | UpdateFirmware triggers FirmwareStatusNotification | OCPP 1.6 §5.8 | Status notification received | INFO |
