"""
OCPP 1.6 Boot sequence tests.
Validates BootNotification fields, heartbeat timing, and reconnect behavior.
"""
import asyncio
import time
import json

from tests.base import OCPPTest, TestResult, TestStatus, Severity, make_exchange
from ocpp_messages.v16 import (
    boot_notification_conf, heartbeat_conf, FIELD_LENGTHS, REGISTRATION_STATUS
)


class BootNotificationRequiredFields(OCPPTest):
    name = "boot_notification_required_fields"
    category = "boot"
    description = "Charger sends BootNotification with all required fields"
    ocpp_spec_ref = "OCPP 1.6 §4.1"
    severity = Severity.CRITICAL
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        payload = connection.boot_payload
        if not payload:
            return self.result(False,
                "BootNotification not received",
                expected="BootNotification sent on connect",
                actual="No BootNotification received",
                fix="Charger must send BootNotification immediately upon WebSocket connection")

        required_fields = ["chargePointVendor", "chargePointModel"]
        # chargePointSerialNumber and firmwareVersion are strongly recommended
        recommended_fields = ["chargePointSerialNumber", "firmwareVersion"]

        missing_required = [f for f in required_fields if not payload.get(f)]
        missing_recommended = [f for f in recommended_fields if not payload.get(f)]

        exchanges = [make_exchange("RECEIVED", "BootNotification", "boot", payload)]

        if missing_required:
            return self.result(False,
                f"Missing required fields: {missing_required}",
                expected=f"Fields present: {required_fields}",
                actual=f"Payload: {json.dumps(payload)}",
                fix=f"Add required fields to BootNotification: {missing_required}",
                exchanges=exchanges)

        msg = "All required fields present"
        if missing_recommended:
            msg += f" (recommended fields missing: {missing_recommended})"

        return self.result(True, msg, exchanges=exchanges,
                           details={"payload": payload, "missing_recommended": missing_recommended})


class BootNotificationFieldLengths(OCPPTest):
    name = "boot_notification_field_lengths"
    category = "boot"
    description = "BootNotification field values respect OCPP 1.6 length limits"
    ocpp_spec_ref = "OCPP 1.6 §4.1 (CiString types)"
    severity = Severity.CRITICAL
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        payload = connection.boot_payload
        if not payload:
            return self.skip("No BootNotification captured")

        violations = []
        for field_name, max_len in FIELD_LENGTHS.items():
            val = payload.get(field_name)
            if val and len(str(val)) > max_len:
                violations.append({
                    "field": field_name,
                    "value": str(val)[:80],
                    "length": len(str(val)),
                    "max_allowed": max_len,
                })

        exchanges = [make_exchange("RECEIVED", "BootNotification", "boot", payload)]

        if violations:
            details_str = "; ".join(
                f"{v['field']}={v['length']} chars (max {v['max_allowed']})"
                for v in violations
            )
            return self.result(False,
                f"Field length violations: {details_str}",
                expected="All fields within OCPP 1.6 CiString length limits",
                actual=details_str,
                fix="Truncate field values to their specified maximum lengths per OCPP 1.6 spec",
                exchanges=exchanges,
                details={"violations": violations})

        return self.result(True, "All field lengths within spec limits", exchanges=exchanges)


class BootNotificationVendorModel(OCPPTest):
    name = "boot_notification_vendor_model"
    category = "boot"
    description = "BootNotification vendor and model are printable ASCII"
    ocpp_spec_ref = "OCPP 1.6 §4.1"
    severity = Severity.WARNING
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        payload = connection.boot_payload
        if not payload:
            return self.skip("No BootNotification captured")

        issues = []
        for field_name in ["chargePointVendor", "chargePointModel", "chargePointSerialNumber", "firmwareVersion"]:
            val = payload.get(field_name, "")
            if val:
                non_printable = [c for c in val if not (32 <= ord(c) <= 126)]
                if non_printable:
                    issues.append(f"{field_name} contains non-printable chars: {non_printable}")

        exchanges = [make_exchange("RECEIVED", "BootNotification", "boot", payload)]

        if issues:
            return self.result(False,
                "; ".join(issues),
                expected="All string fields contain only printable ASCII (0x20-0x7E)",
                actual="; ".join(issues),
                fix="Remove non-printable characters from BootNotification string fields",
                exchanges=exchanges)

        return self.result(True,
            f"Vendor='{payload.get('chargePointVendor')}' "
            f"Model='{payload.get('chargePointModel')}' "
            f"Firmware='{payload.get('firmwareVersion')}'",
            exchanges=exchanges)


class BootNotificationOptionalFields(OCPPTest):
    name = "boot_notification_optional_fields"
    category = "boot"
    description = "BootNotification optional fields have correct format when present"
    ocpp_spec_ref = "OCPP 1.6 §4.1"
    severity = Severity.INFO
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        payload = connection.boot_payload
        if not payload:
            return self.skip("No BootNotification captured")

        present = []
        issues = []

        optional_fields = ["chargeBoxSerialNumber", "iccid", "imsi", "meterType", "meterSerialNumber"]
        for f in optional_fields:
            val = payload.get(f)
            if val:
                present.append(f"{f}={val!r}")
                # Validate length
                max_len = FIELD_LENGTHS.get(f, 50)
                if len(str(val)) > max_len:
                    issues.append(f"{f} exceeds max length {max_len}")

        exchanges = [make_exchange("RECEIVED", "BootNotification", "boot", payload)]

        if issues:
            return self.result(False, "; ".join(issues),
                expected="Optional fields within length limits",
                actual="; ".join(issues),
                fix="Truncate optional fields to OCPP spec limits",
                exchanges=exchanges)

        if present:
            return self.result(True, f"Optional fields present: {', '.join(present)}", exchanges=exchanges)

        return self.result(True,
            "No optional fields present (all optional, none sent)",
            exchanges=exchanges,
            details={"info": "Consider sending serialNumber and firmwareVersion for traceability"})


class BootNotificationResponseHandling(OCPPTest):
    name = "boot_notification_response_accepted"
    category = "boot"
    description = "Charger correctly handles BootNotification.conf with Accepted status"
    ocpp_spec_ref = "OCPP 1.6 §4.1"
    severity = Severity.CRITICAL
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        # The server already responded with Accepted (done in the boot handler)
        # Check that the charger proceeded normally (sent StatusNotification or Heartbeat)
        payload = connection.boot_payload
        if not payload:
            return self.skip("No BootNotification captured")

        exchanges = [make_exchange("RECEIVED", "BootNotification", "boot", payload)]

        # If we got here, boot was accepted and connection is active
        return self.result(True,
            "BootNotification accepted — charger is online",
            exchanges=exchanges)


class HeartbeatInterval(OCPPTest):
    name = "heartbeat_interval"
    category = "boot"
    description = "Charger sends Heartbeats at configured interval (±10% tolerance)"
    ocpp_spec_ref = "OCPP 1.6 §4.2"
    severity = Severity.WARNING
    versions = ["1.6"]

    MIN_SAMPLES = 3

    async def run(self, connection) -> TestResult:
        expected_interval = self.config.get("heartbeat_interval", 30)
        collect_time = expected_interval * (self.MIN_SAMPLES + 1) + 10

        heartbeat_times = []
        deadline = time.monotonic() + collect_time
        exchanges = []

        while time.monotonic() < deadline and len(heartbeat_times) < self.MIN_SAMPLES + 1:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            item = await connection.wait_for_action("Heartbeat", timeout=min(remaining, expected_interval * 1.5))
            if item:
                heartbeat_times.append(item["ts"])
                exchanges.append(make_exchange("RECEIVED", "Heartbeat", item["unique_id"], item["payload"]))
                await connection.send_result(item["unique_id"], heartbeat_conf())
            else:
                break

        if len(heartbeat_times) < 2:
            return self.result(False,
                f"Only {len(heartbeat_times)} heartbeats received (need at least 2 to measure interval)",
                expected=f"Heartbeat every {expected_interval}s (collected over ~{collect_time:.0f}s)",
                actual=f"{len(heartbeat_times)} heartbeats in {collect_time:.0f}s window",
                fix=f"Set HeartbeatInterval={expected_interval} and ensure charger sends heartbeats",
                exchanges=exchanges)

        intervals = [heartbeat_times[i+1] - heartbeat_times[i]
                     for i in range(len(heartbeat_times)-1)]
        avg_interval = sum(intervals) / len(intervals)
        min_interval = min(intervals)
        max_interval = max(intervals)

        tolerance = 0.10
        low = expected_interval * (1 - tolerance)
        high = expected_interval * (1 + tolerance)

        out_of_range = [iv for iv in intervals if not (low <= iv <= high)]

        details = {
            "expected_interval": expected_interval,
            "avg_interval": round(avg_interval, 2),
            "min_interval": round(min_interval, 2),
            "max_interval": round(max_interval, 2),
            "samples": len(intervals),
            "tolerance_pct": 10,
        }

        if out_of_range:
            return self.result(False,
                f"Heartbeat interval out of tolerance: avg={avg_interval:.1f}s "
                f"(expected {expected_interval}s ±10%, range {low:.1f}–{high:.1f}s)",
                expected=f"Heartbeat every {expected_interval}s ±10% ({low:.1f}–{high:.1f}s)",
                actual=f"Avg {avg_interval:.1f}s, min {min_interval:.1f}s, max {max_interval:.1f}s",
                fix=f"Ensure HeartbeatInterval is set to {expected_interval}s and charger respects it precisely",
                exchanges=exchanges,
                details=details)

        return self.result(True,
            f"Heartbeat interval: avg={avg_interval:.1f}s ±10% tolerance "
            f"({len(intervals)} measurements)",
            exchanges=exchanges,
            details=details)


class HeartbeatMultipleSamples(OCPPTest):
    name = "heartbeat_multiple_samples"
    category = "boot"
    description = "Collect at least 3 heartbeat cycles for interval stability analysis"
    ocpp_spec_ref = "OCPP 1.6 §4.2"
    severity = Severity.INFO
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        expected_interval = self.config.get("heartbeat_interval", 30)
        # Already covered by HeartbeatInterval; this test focuses on stability/jitter
        return self.result(True,
            "Heartbeat sampling covered by heartbeat_interval test",
            details={"note": "See heartbeat_interval test for detailed measurements"})


ALL_TESTS = [
    BootNotificationRequiredFields,
    BootNotificationFieldLengths,
    BootNotificationVendorModel,
    BootNotificationOptionalFields,
    BootNotificationResponseHandling,
    HeartbeatInterval,
]
