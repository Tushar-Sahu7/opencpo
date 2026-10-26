"""
OCPP 1.6 Firmware and Diagnostics tests.
These are optional/manual tests requiring network access from charger.
"""
import asyncio
import time

from tests.base import OCPPTest, TestResult, Severity, make_exchange
from ocpp_messages.v16 import (
    update_firmware_conf, get_diagnostics_conf,
    FIRMWARE_STATUS, DIAGNOSTICS_STATUS
)


class UpdateFirmwareFlow(OCPPTest):
    name = "update_firmware_flow"
    category = "firmware"
    description = "UpdateFirmware → FirmwareStatusNotification sequence"
    ocpp_spec_ref = "OCPP 1.6 §8.2"
    severity = Severity.INFO
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        fw_url = self.config.get("firmware", {}).get("url")
        if not fw_url:
            return self.skip("No firmware URL configured (set firmware.url in config.yaml)")

        from datetime import datetime, timezone
        exchanges = []

        payload = {
            "location": fw_url,
            "retrieveDate": datetime.now(timezone.utc).isoformat(),
        }
        # Send UpdateFirmware — no response expected (it's a request with no response payload)
        uid, _ = await connection.send_call(
            "UpdateFirmware", payload
        )
        exchanges.append(make_exchange("SENT", "UpdateFirmware", uid, payload))

        # Wait for FirmwareStatusNotification sequence
        # Expected: Downloading → Downloaded → Installing → Installed (or InstallationFailed)
        expected_sequence = ["Downloading", "Downloaded", "Installing"]
        final_statuses = {"Installed", "InstallationFailed"}

        received_statuses = []
        timeout = 300  # 5 minutes max for firmware download
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            item = await connection.wait_for_action(
                "FirmwareStatusNotification", timeout=min(remaining, 30.0)
            )
            if not item:
                break

            fw_status = item["payload"].get("status", "")
            received_statuses.append(fw_status)
            exchanges.append(
                make_exchange("RECEIVED", "FirmwareStatusNotification",
                              item["unique_id"], item["payload"])
            )
            await connection.send_result(item["unique_id"], {})

            if fw_status in final_statuses:
                break

        if not received_statuses:
            return self.result(False,
                "No FirmwareStatusNotification received after UpdateFirmware",
                expected="Sequence: Downloading → Downloaded → Installing → Installed",
                actual="No FirmwareStatusNotification received",
                fix="After receiving UpdateFirmware, send FirmwareStatusNotification "
                    "messages to track download/install progress",
                exchanges=exchanges)

        # Check for invalid status values
        invalid_statuses = [s for s in received_statuses if s not in FIRMWARE_STATUS]
        if invalid_statuses:
            return self.result(False,
                f"Invalid FirmwareStatus values: {invalid_statuses}",
                expected=f"Status values from: {sorted(FIRMWARE_STATUS)}",
                actual=str(received_statuses),
                fix=f"Use only valid FirmwareStatus values: {sorted(FIRMWARE_STATUS)}",
                exchanges=exchanges)

        final = received_statuses[-1]
        passed = final == "Installed"

        return self.result(passed,
            f"Firmware update sequence: {' → '.join(received_statuses)}",
            expected="Downloading → Downloaded → Installing → Installed",
            actual=" → ".join(received_statuses),
            fix="Ensure firmware download, install, and verification complete successfully" if not passed else "",
            exchanges=exchanges)


class GetDiagnosticsFlow(OCPPTest):
    name = "get_diagnostics_flow"
    category = "firmware"
    description = "GetDiagnostics → DiagnosticsStatusNotification sequence"
    ocpp_spec_ref = "OCPP 1.6 §8.1"
    severity = Severity.INFO
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        diag_url = self.config.get("diagnostics", {}).get("upload_url")
        if not diag_url:
            return self.skip("No diagnostics upload URL configured (set diagnostics.upload_url)")

        from datetime import datetime, timezone
        exchanges = []

        payload = {
            "location": diag_url,
        }
        resp = await connection.send_call_and_wait("GetDiagnostics", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "GetDiagnostics", "gd", payload))

        if resp is None:
            return self.result(False, "GetDiagnostics timed out", exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "GetDiagnostics.conf", "gd", resp))

        if resp.get("_is_error"):
            ec = resp.get("error_code", "")
            if ec in ("NotImplemented", "NotSupported"):
                return self.skip("GetDiagnostics not supported")
            return self.result(False, f"GetDiagnostics error: {ec}", exchanges=exchanges)

        file_name = resp.get("fileName")
        if file_name:
            exchanges[-1].payload["fileName"] = file_name

        # Wait for DiagnosticsStatusNotification
        received_statuses = []
        deadline = time.monotonic() + 120  # 2 minutes

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            item = await connection.wait_for_action(
                "DiagnosticsStatusNotification", timeout=min(remaining, 20.0)
            )
            if not item:
                break

            diag_status = item["payload"].get("status", "")
            received_statuses.append(diag_status)
            exchanges.append(
                make_exchange("RECEIVED", "DiagnosticsStatusNotification",
                              item["unique_id"], item["payload"])
            )
            await connection.send_result(item["unique_id"], {})

            if diag_status in ("Uploaded", "UploadFailed"):
                break

        if not received_statuses:
            return self.result(False,
                "No DiagnosticsStatusNotification received",
                expected="Uploading → Uploaded (or UploadFailed)",
                actual="No DiagnosticsStatusNotification received",
                exchanges=exchanges)

        invalid = [s for s in received_statuses if s not in DIAGNOSTICS_STATUS]
        if invalid:
            return self.result(False,
                f"Invalid DiagnosticsStatus values: {invalid}",
                expected=f"Values from: {sorted(DIAGNOSTICS_STATUS)}",
                actual=str(received_statuses),
                exchanges=exchanges)

        final = received_statuses[-1]
        return self.result(final == "Uploaded",
            f"Diagnostics sequence: {' → '.join(received_statuses)}",
            exchanges=exchanges)


ALL_TESTS = [
    UpdateFirmwareFlow,
    GetDiagnosticsFlow,
]
