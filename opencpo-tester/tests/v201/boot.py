"""
OCPP 2.0.1 Boot sequence tests.
BootNotification now includes ChargingStation object with model, vendorName, etc.
"""
import json
import re
import time

from tests.base import OCPPTest, TestResult, Severity, make_exchange
from ocpp_messages.v201 import boot_notification_conf, heartbeat_conf, REGISTRATION_STATUS


class BootNotification201RequiredFields(OCPPTest):
    name = "boot201_required_fields"
    category = "boot"
    description = "BootNotification includes ChargingStation with required fields"
    ocpp_spec_ref = "OCPP 2.0.1 §4.2"
    severity = Severity.CRITICAL
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        payload = connection.boot_payload
        if not payload:
            return self.result(False,
                "BootNotification not received",
                expected="BootNotification on connect",
                actual="No BootNotification received",
                fix="Send BootNotification with ChargingStation object on connect")

        # 2.0.1 has ChargingStation sub-object
        cs = payload.get("chargingStation")
        reason = payload.get("reason")
        exchanges = [make_exchange("RECEIVED", "BootNotification", "boot201", payload)]

        issues = []
        if not cs:
            issues.append("Missing 'chargingStation' object")
        else:
            if not cs.get("model"):
                issues.append("chargingStation.model missing")
            elif len(cs["model"]) > 20:
                issues.append(f"chargingStation.model too long: {len(cs['model'])} chars (max 20)")

            if not cs.get("vendorName"):
                issues.append("chargingStation.vendorName missing")
            elif len(cs["vendorName"]) > 50:
                issues.append(f"chargingStation.vendorName too long: {len(cs['vendorName'])} chars (max 50)")

        if not reason:
            issues.append("Missing 'reason' field (ApplicationReset/FirmwareUpdate/LocalReset/PowerUp/RemoteReset/ScheduledReset/Triggered/Unknown/Watchdog)")

        if issues:
            return self.result(False,
                f"BootNotification 2.0.1 field violations: {'; '.join(issues)}",
                expected="chargingStation: {model, vendorName} + reason",
                actual=f"Payload: {json.dumps(payload)}",
                fix="Include chargingStation.model (max 20 chars), chargingStation.vendorName (max 50 chars), "
                    "and reason (e.g. 'PowerUp') in BootNotification",
                exchanges=exchanges)

        # Store charger info
        if cs:
            connection.vendor = cs.get("vendorName", "")
            connection.model = cs.get("model", "")
            connection.serial = cs.get("serialNumber", "")
            connection.firmware = cs.get("firmwareVersion", "")

        return self.result(True,
            f"BootNotification 2.0.1 valid: model={cs.get('model')} vendor={cs.get('vendorName')} reason={reason}",
            exchanges=exchanges,
            details={"payload": payload})


class BootNotification201ModemInfo(OCPPTest):
    name = "boot201_modem_info"
    category = "boot"
    description = "Optional chargingStation.modem fields (iccid, imsi) are within length limits"
    ocpp_spec_ref = "OCPP 2.0.1 §4.2"
    severity = Severity.INFO
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        payload = connection.boot_payload
        if not payload:
            return self.skip("No BootNotification captured")

        cs = payload.get("chargingStation", {})
        modem = cs.get("modem", {})

        if not modem:
            return self.result(True, "No modem info provided (optional)")

        issues = []
        iccid = modem.get("iccid", "")
        imsi = modem.get("imsi", "")

        if iccid and len(iccid) > 20:
            issues.append(f"iccid too long: {len(iccid)} chars (max 20)")
        if imsi and len(imsi) > 20:
            issues.append(f"imsi too long: {len(imsi)} chars (max 20)")

        exchanges = [make_exchange("RECEIVED", "BootNotification", "boot201", payload)]

        if issues:
            return self.result(False, "; ".join(issues), exchanges=exchanges)

        return self.result(True,
            f"Modem info: iccid={iccid!r} imsi={imsi!r}",
            exchanges=exchanges)


class HeartbeatInterval201(OCPPTest):
    name = "heartbeat201_interval"
    category = "boot"
    description = "Charger sends Heartbeats at configured interval (±10%)"
    ocpp_spec_ref = "OCPP 2.0.1 §4.4"
    severity = Severity.WARNING
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        expected_interval = self.config.get("heartbeat_interval", 30)
        heartbeat_times = []
        deadline = time.monotonic() + expected_interval * 4

        while time.monotonic() < deadline and len(heartbeat_times) < 4:
            remaining = deadline - time.monotonic()
            item = await connection.wait_for_action("Heartbeat", timeout=min(remaining, expected_interval * 1.5))
            if item:
                heartbeat_times.append(item["ts"])
                await connection.send_result(item["unique_id"], heartbeat_conf())
            else:
                break

        if len(heartbeat_times) < 2:
            return self.result(False,
                f"Only {len(heartbeat_times)} heartbeats in window",
                expected=f"Heartbeat every {expected_interval}s",
                actual=f"{len(heartbeat_times)} heartbeats",
                fix=f"Configure HeartbeatInterval={expected_interval}")

        intervals = [heartbeat_times[i+1] - heartbeat_times[i] for i in range(len(heartbeat_times)-1)]
        avg = sum(intervals) / len(intervals)
        low = expected_interval * 0.9
        high = expected_interval * 1.1

        if any(not (low <= iv <= high) for iv in intervals):
            return self.result(False,
                f"Heartbeat interval avg={avg:.1f}s out of {expected_interval}±10% range",
                expected=f"{expected_interval}s ±10% ({low:.1f}–{high:.1f}s)",
                actual=f"avg={avg:.1f}s")

        return self.result(True, f"Heartbeat interval OK: avg={avg:.1f}s")


ALL_TESTS = [
    BootNotification201RequiredFields,
    BootNotification201ModemInfo,
    HeartbeatInterval201,
]
