"""
OCPP 2.0.1 Firmware Management tests.
UpdateFirmware replaces 1.6 UpdateFirmware with a new FirmwareStatusNotification enum.
GetLog (diagnostics) replaces GetDiagnostics.
"""
import time

from tests.base import OCPPTest, TestResult, Severity, make_exchange

# OCPP 2.0.1 FirmwareStatus enum
FIRMWARE_STATUS_201 = {
    "Downloaded",
    "DownloadFailed",
    "Downloading",
    "DownloadScheduled",
    "DownloadPaused",
    "Idle",
    "InstallationFailed",
    "Installing",
    "Installed",
    "InstallRebooting",
    "InstallScheduled",
    "InstallVerificationFailed",
    "InvalidSignature",
    "SignatureVerified",
}

# Final statuses (stop waiting)
FIRMWARE_FINAL_STATUS_201 = {
    "Installed",
    "InstallationFailed",
    "DownloadFailed",
    "InvalidSignature",
    "InstallVerificationFailed",
}

# OCPP 2.0.1 UploadLogStatus enum
LOG_STATUS_201 = {
    "BadMessage", "Idle", "NotSupportedOperation", "PermissionDenied",
    "Uploaded", "UploadFailure", "Uploading", "AcceptedCanceled",
}


class UpdateFirmware201Flow(OCPPTest):
    name = "update_firmware_201_flow"
    category = "firmware"
    description = "UpdateFirmware (2.0.1) → FirmwareStatusNotification sequence with valid status values"
    ocpp_spec_ref = "OCPP 2.0.1 §8.2"
    severity = Severity.INFO
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        fw_url = self.config.get("firmware", {}).get("url")
        if not fw_url:
            return self.skip("No firmware URL configured (set firmware.url in config.yaml)")

        from datetime import datetime, timezone
        exchanges = []

        payload = {
            "requestId": 1,
            "firmware": {
                "location": fw_url,
                "retrieveDateTime": datetime.now(timezone.utc).isoformat(),
            },
        }
        resp = await connection.send_call_and_wait("UpdateFirmware", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "UpdateFirmware", "uf201", payload))

        if resp is None:
            return self.result(False, "UpdateFirmware timed out", exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "UpdateFirmware.conf", "uf201", resp))

        if resp.get("_is_error"):
            ec = resp.get("error_code", "")
            if ec in ("NotImplemented", "NotSupported"):
                return self.skip("UpdateFirmware not supported")
            return self.result(False, f"UpdateFirmware error: {ec}", exchanges=exchanges)

        update_status = resp.get("status", "")
        valid_update_statuses = {
            "Accepted", "Rejected", "AcceptedCanceled", "InvalidCertificate", "RevokedCertificate"
        }
        if update_status and update_status not in valid_update_statuses:
            return self.result(False,
                f"Invalid UpdateFirmware status: '{update_status}'",
                expected=f"One of: {sorted(valid_update_statuses)}",
                actual=f"'{update_status}'",
                exchanges=exchanges)

        if update_status == "Rejected":
            return self.result(True, "UpdateFirmware Rejected (acceptable)", exchanges=exchanges)

        # Wait for FirmwareStatusNotification sequence
        received_statuses = []
        deadline = time.monotonic() + 300  # 5 minutes max

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            item = await connection.wait_for_action(
                "FirmwareStatusNotification", timeout=min(remaining, 30.0)
            )
            if not item:
                break

            fw_status = item["payload"].get("status", "")
            received_statuses.append(fw_status)
            exchanges.append(make_exchange(
                "RECEIVED", "FirmwareStatusNotification", item["unique_id"], item["payload"]
            ))
            await connection.send_result(item["unique_id"], {})

            if fw_status in FIRMWARE_FINAL_STATUS_201:
                break

        if not received_statuses:
            return self.result(False,
                "No FirmwareStatusNotification received after UpdateFirmware",
                expected="FirmwareStatusNotification sequence (Downloading → Downloaded → Installing → Installed)",
                actual="No FirmwareStatusNotification received",
                fix="Send FirmwareStatusNotification to report download/install progress",
                exchanges=exchanges)

        # Validate status values
        invalid = [s for s in received_statuses if s not in FIRMWARE_STATUS_201]
        if invalid:
            return self.result(False,
                f"Invalid FirmwareStatus values: {invalid}",
                expected=f"Values from: {sorted(FIRMWARE_STATUS_201)}",
                actual=str(received_statuses),
                fix=f"Use only valid OCPP 2.0.1 FirmwareStatus values: {sorted(FIRMWARE_STATUS_201)}",
                exchanges=exchanges)

        final = received_statuses[-1]
        passed = final == "Installed"

        return self.result(passed,
            f"Firmware sequence: {' → '.join(received_statuses)}",
            expected="… → Installed",
            actual=" → ".join(received_statuses),
            fix="Ensure firmware download, signature verification, and installation complete successfully" if not passed else "",
            exchanges=exchanges)


class FirmwareStatusNotification201ValidStatus(OCPPTest):
    name = "firmware_status_201_valid_status"
    category = "firmware"
    description = "FirmwareStatusNotification messages use valid 2.0.1 status enum values"
    ocpp_spec_ref = "OCPP 2.0.1 §8.2"
    severity = Severity.WARNING
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        log_entries = connection.log.get_all()
        fw_notifications = []
        for e in log_entries:
            if e.get("parsed") and isinstance(e["parsed"], list):
                msg = e["parsed"]
                if msg[0] == 2 and msg[2] == "FirmwareStatusNotification":
                    fw_notifications.append({"uid": msg[1], "payload": msg[3]})

        if not fw_notifications:
            return self.skip("No FirmwareStatusNotification messages captured")

        violations = []
        exchanges = []
        for fwn in fw_notifications:
            exchanges.append(make_exchange("RECEIVED", "FirmwareStatusNotification",
                                          fwn["uid"], fwn["payload"]))
            status = fwn["payload"].get("status", "")
            if status not in FIRMWARE_STATUS_201:
                violations.append(f"Invalid status: '{status}'")

        if violations:
            return self.result(False,
                "; ".join(violations),
                expected=f"Status from: {sorted(FIRMWARE_STATUS_201)}",
                actual="; ".join(violations),
                fix=f"Use only valid OCPP 2.0.1 FirmwareStatus values",
                exchanges=exchanges)

        statuses = [fwn["payload"].get("status") for fwn in fw_notifications]
        return self.result(True,
            f"All FirmwareStatusNotification values valid: {statuses}",
            exchanges=exchanges)


class GetLog201Flow(OCPPTest):
    name = "get_log_201_flow"
    category = "firmware"
    description = "GetLog (Diagnostics) → LogStatusNotification sequence"
    ocpp_spec_ref = "OCPP 2.0.1 §8.1"
    severity = Severity.INFO
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        log_url = self.config.get("diagnostics", {}).get("upload_url")
        if not log_url:
            return self.skip("No diagnostics upload URL configured (set diagnostics.upload_url)")

        from datetime import datetime, timezone
        exchanges = []
        payload = {
            "logType": "DiagnosticsLog",
            "requestId": 2,
            "log": {
                "remoteLocation": log_url,
            },
        }
        resp = await connection.send_call_and_wait("GetLog", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "GetLog", "gl201", payload))

        if resp is None:
            return self.result(False, "GetLog timed out", exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "GetLog.conf", "gl201", resp))

        if resp.get("_is_error"):
            ec = resp.get("error_code", "")
            if ec in ("NotImplemented", "NotSupported"):
                return self.skip("GetLog not supported")
            return self.result(False, f"GetLog error: {ec}", exchanges=exchanges)

        status = resp.get("status", "")
        valid = {"Accepted", "Rejected", "AcceptedCanceled", "NoLogs"}
        if status not in valid:
            return self.result(False,
                f"Invalid GetLog status: '{status}'",
                expected=f"One of: {sorted(valid)}",
                actual=f"'{status}'",
                exchanges=exchanges)

        if status in ("Rejected", "NoLogs"):
            return self.result(True,
                f"GetLog → {status} (acceptable)",
                exchanges=exchanges)

        # Wait for LogStatusNotification
        received_statuses = []
        deadline = time.monotonic() + 120

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            item = await connection.wait_for_action(
                "LogStatusNotification", timeout=min(remaining, 20.0)
            )
            if not item:
                break

            log_status = item["payload"].get("status", "")
            received_statuses.append(log_status)
            exchanges.append(make_exchange(
                "RECEIVED", "LogStatusNotification", item["unique_id"], item["payload"]
            ))
            await connection.send_result(item["unique_id"], {})

            if log_status in ("Uploaded", "UploadFailure", "BadMessage", "PermissionDenied"):
                break

        if not received_statuses:
            return self.result(False,
                "No LogStatusNotification received",
                expected="LogStatusNotification after GetLog(Accepted)",
                actual="No LogStatusNotification",
                fix="Send LogStatusNotification to report upload progress",
                exchanges=exchanges)

        invalid = [s for s in received_statuses if s not in LOG_STATUS_201]
        if invalid:
            return self.result(False,
                f"Invalid LogStatus values: {invalid}",
                expected=f"Values from: {sorted(LOG_STATUS_201)}",
                actual=str(received_statuses),
                exchanges=exchanges)

        final = received_statuses[-1]
        return self.result(final == "Uploaded",
            f"Log upload sequence: {' → '.join(received_statuses)}",
            exchanges=exchanges)


ALL_TESTS = [
    UpdateFirmware201Flow,
    FirmwareStatusNotification201ValidStatus,
    GetLog201Flow,
]
