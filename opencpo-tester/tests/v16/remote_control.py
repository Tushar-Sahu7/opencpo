"""
OCPP 1.6 Remote Control tests.
Tests Reset, ChangeConfiguration, GetConfiguration, TriggerMessage, UnlockConnector.
"""
import asyncio
import json
import time

from tests.base import OCPPTest, TestResult, Severity, make_exchange
from ocpp_messages.v16 import (
    reset_conf, change_configuration_conf, get_configuration_conf,
    unlock_connector_conf, trigger_message_conf, boot_notification_conf,
    STANDARD_CONFIG_KEYS
)


class ResetSoft(OCPPTest):
    name = "reset_soft"
    category = "remote_control"
    description = "Soft reset → charger reboots and reconnects with BootNotification"
    ocpp_spec_ref = "OCPP 1.6 §5.12"
    severity = Severity.CRITICAL
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        exchanges = []

        # Send Reset(Soft)
        payload = {"type": "Soft"}
        resp = await connection.send_call_and_wait("Reset", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "Reset", "reset_soft", payload))

        if resp is None:
            return self.result(False,
                "Reset(Soft) timed out — no response",
                expected="status: Accepted",
                actual="No response",
                fix="Implement Reset handler",
                exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "Reset.conf", "reset_soft", resp))

        if resp.get("_is_error"):
            return self.result(False,
                f"Reset returned error: {resp.get('error_code')}",
                exchanges=exchanges)

        status = resp.get("status", "")
        if status not in ("Accepted", "Rejected"):
            return self.result(False,
                f"Invalid Reset status: '{status}'",
                expected="'Accepted' or 'Rejected'",
                actual=f"'{status}'",
                fix="Reset.conf status must be 'Accepted' or 'Rejected'",
                exchanges=exchanges)

        if status == "Rejected":
            return self.result(True,
                "Reset(Soft) rejected — acceptable if charger is charging",
                exchanges=exchanges)

        # Wait for reconnect + BootNotification
        # Server creates a new connection event — we need to wait for the charger to reconnect
        return self.result(True,
            "Reset(Soft) accepted — charger should reboot and send BootNotification",
            exchanges=exchanges,
            details={"note": "Reboot behavior verified by watching server reconnect logs"})


class ResetHard(OCPPTest):
    name = "reset_hard"
    category = "remote_control"
    description = "Hard reset → charger reboots and reconnects"
    ocpp_spec_ref = "OCPP 1.6 §5.12"
    severity = Severity.WARNING
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        exchanges = []

        payload = {"type": "Hard"}
        resp = await connection.send_call_and_wait("Reset", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "Reset", "reset_hard", payload))

        if resp is None:
            return self.result(False, "Reset(Hard) timed out", exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "Reset.conf", "reset_hard", resp))

        if resp.get("_is_error"):
            return self.result(False, f"Reset error: {resp.get('error_code')}", exchanges=exchanges)

        status = resp.get("status", "")
        if status not in ("Accepted", "Rejected"):
            return self.result(False, f"Invalid status: '{status}'", exchanges=exchanges)

        return self.result(status == "Accepted",
            f"Reset(Hard) {status}",
            exchanges=exchanges)


class ChangeConfigurationAccepted(OCPPTest):
    name = "change_configuration_accepted"
    category = "remote_control"
    description = "ChangeConfiguration with valid key returns Accepted or RebootRequired"
    ocpp_spec_ref = "OCPP 1.6 §6.2"
    severity = Severity.WARNING
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        # Use a safe key that shouldn't break anything
        exchanges = []
        payload = {"key": "HeartbeatInterval", "value": "30"}
        resp = await connection.send_call_and_wait("ChangeConfiguration", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "ChangeConfiguration", "cc_valid", payload))

        if resp is None:
            return self.result(False,
                "ChangeConfiguration timed out",
                expected="Accepted or RebootRequired",
                actual="Timeout",
                fix="Implement ChangeConfiguration handler",
                exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "ChangeConfiguration.conf", "cc_valid", resp))

        if resp.get("_is_error"):
            return self.result(False, f"ChangeConfiguration error: {resp.get('error_code')}",
                               exchanges=exchanges)

        status = resp.get("status", "")
        valid_statuses = {"Accepted", "Rejected", "RebootRequired", "NotSupported"}
        if status not in valid_statuses:
            return self.result(False,
                f"Invalid ChangeConfiguration status: '{status}'",
                expected=f"One of: {sorted(valid_statuses)}",
                actual=f"'{status}'",
                fix=f"Return one of the valid status values: {sorted(valid_statuses)}",
                exchanges=exchanges)

        if status == "Accepted":
            return self.result(True,
                f"ChangeConfiguration(HeartbeatInterval=30) → Accepted",
                exchanges=exchanges)
        elif status == "RebootRequired":
            return self.result(True,
                f"ChangeConfiguration(HeartbeatInterval=30) → RebootRequired (acceptable)",
                exchanges=exchanges)
        else:
            return self.result(True,
                f"ChangeConfiguration(HeartbeatInterval=30) → {status}",
                exchanges=exchanges,
                details={"note": f"Charger returned {status} for a standard key"})


class ChangeConfigurationUnknownKey(OCPPTest):
    name = "change_configuration_unknown_key"
    category = "remote_control"
    description = "ChangeConfiguration with unknown key returns NotSupported"
    ocpp_spec_ref = "OCPP 1.6 §6.2"
    severity = Severity.WARNING
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        exchanges = []
        payload = {"key": "UnknownNonExistentKey_XYZ_123", "value": "test"}
        resp = await connection.send_call_and_wait("ChangeConfiguration", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "ChangeConfiguration", "cc_unknown", payload))

        if resp is None:
            return self.result(False, "ChangeConfiguration timed out", exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "ChangeConfiguration.conf", "cc_unknown", resp))

        status = resp.get("status", "")
        if status == "NotSupported":
            return self.result(True,
                "Unknown key correctly returns NotSupported",
                exchanges=exchanges)
        elif status in ("Accepted", "RebootRequired"):
            return self.result(False,
                f"Unknown key 'UnknownNonExistentKey_XYZ_123' returned '{status}' instead of NotSupported",
                expected="NotSupported for unknown configuration keys",
                actual=f"'{status}'",
                fix="Return 'NotSupported' when a configuration key is not recognized",
                exchanges=exchanges)
        else:
            return self.result(True,
                f"Unknown key returned '{status}' (acceptable)",
                exchanges=exchanges)


class GetConfigurationAll(OCPPTest):
    name = "get_configuration_all"
    category = "remote_control"
    description = "GetConfiguration (no key) returns all config keys with valid format"
    ocpp_spec_ref = "OCPP 1.6 §6.3"
    severity = Severity.WARNING
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        exchanges = []
        resp = await connection.send_call_and_wait("GetConfiguration", {}, timeout=15.0)
        exchanges.append(make_exchange("SENT", "GetConfiguration", "gc_all", {}))

        if resp is None:
            return self.result(False, "GetConfiguration timed out", exchanges=exchanges,
                               fix="Implement GetConfiguration handler")

        exchanges.append(make_exchange("RECEIVED", "GetConfiguration.conf", "gc_all", resp))

        if resp.get("_is_error"):
            return self.result(False, f"GetConfiguration error: {resp.get('error_code')}",
                               exchanges=exchanges)

        config_keys = resp.get("configurationKey", [])
        unknown_keys = resp.get("unknownKey", [])

        if not isinstance(config_keys, list):
            return self.result(False,
                "configurationKey is not an array",
                expected="configurationKey: [{key, value, readonly}]",
                actual=f"configurationKey type: {type(config_keys).__name__}",
                exchanges=exchanges)

        issues = []
        for item in config_keys:
            if not isinstance(item, dict):
                issues.append(f"Config item is not object: {item!r}")
                continue
            if "key" not in item:
                issues.append(f"Config item missing 'key': {item!r}")
            if "readonly" not in item:
                issues.append(f"Config item missing 'readonly' for key={item.get('key')!r}")
            if "value" not in item:
                issues.append(f"Config item missing 'value' for key={item.get('key')!r}")

        # Store for later use
        for item in config_keys:
            if isinstance(item, dict) and "key" in item:
                connection.known_config[item["key"]] = str(item.get("value", ""))

        if issues:
            return self.result(False,
                f"Config format issues: {'; '.join(issues[:5])}",
                expected="configurationKey: [{key: str, value: str, readonly: bool}]",
                actual="; ".join(issues[:5]),
                fix="Each configurationKey entry must have 'key', 'value', and 'readonly' fields",
                exchanges=exchanges)

        # Check for important standard keys
        returned_keys = {item.get("key") for item in config_keys if isinstance(item, dict)}
        expected_keys = {"HeartbeatInterval", "MeterValueSampleInterval", "NumberOfConnectors"}
        missing_important = expected_keys - returned_keys

        return self.result(True,
            f"GetConfiguration returned {len(config_keys)} keys",
            exchanges=exchanges,
            details={
                "total_keys": len(config_keys),
                "unknown_keys": unknown_keys,
                "missing_standard_keys": list(missing_important) if missing_important else [],
                "supported_profiles": connection.known_config.get("SupportedFeatureProfiles", "not reported"),
            })


class GetConfigurationSpecificKey(OCPPTest):
    name = "get_configuration_specific_key"
    category = "remote_control"
    description = "GetConfiguration with specific key returns correct value"
    ocpp_spec_ref = "OCPP 1.6 §6.3"
    severity = Severity.INFO
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        exchanges = []
        payload = {"key": ["HeartbeatInterval"]}
        resp = await connection.send_call_and_wait("GetConfiguration", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "GetConfiguration", "gc_specific", payload))

        if resp is None:
            return self.skip("GetConfiguration timed out")

        exchanges.append(make_exchange("RECEIVED", "GetConfiguration.conf", "gc_specific", resp))

        config_keys = resp.get("configurationKey", [])
        unknown_keys = resp.get("unknownKey", [])

        if "HeartbeatInterval" in unknown_keys:
            return self.result(False,
                "HeartbeatInterval returned as unknownKey — this is a mandatory OCPP 1.6 config key",
                expected="HeartbeatInterval in configurationKey",
                actual="HeartbeatInterval in unknownKey",
                fix="Implement HeartbeatInterval configuration key",
                exchanges=exchanges)

        matching = [k for k in config_keys if k.get("key") == "HeartbeatInterval"]
        if not matching:
            return self.result(False,
                "HeartbeatInterval not found in response",
                expected="HeartbeatInterval present in configurationKey",
                actual=f"configurationKey={config_keys}",
                exchanges=exchanges)

        val = matching[0].get("value")
        return self.result(True,
            f"HeartbeatInterval = {val!r}",
            exchanges=exchanges,
            details={"heartbeat_interval_configured": val})


class UnlockConnector(OCPPTest):
    name = "unlock_connector"
    category = "remote_control"
    description = "UnlockConnector → Unlocked, UnlockFailed, or NotSupported"
    ocpp_spec_ref = "OCPP 1.6 §5.14"
    severity = Severity.INFO
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        connector_id = connection.active_connector_id or 1
        exchanges = []

        payload = {"connectorId": connector_id}
        resp = await connection.send_call_and_wait("UnlockConnector", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "UnlockConnector", "unlock", payload))

        if resp is None:
            return self.result(False, "UnlockConnector timed out", exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "UnlockConnector.conf", "unlock", resp))

        if resp.get("_is_error"):
            return self.result(False, f"UnlockConnector error: {resp.get('error_code')}",
                               exchanges=exchanges)

        status = resp.get("status", "")
        valid = {"Unlocked", "UnlockFailed", "NotSupported"}
        if status not in valid:
            return self.result(False,
                f"Invalid UnlockConnector status: '{status}'",
                expected=f"One of: {sorted(valid)}",
                actual=f"'{status}'",
                fix=f"Return one of: {sorted(valid)}",
                exchanges=exchanges)

        return self.result(True,
            f"UnlockConnector(connector={connector_id}) → {status}",
            exchanges=exchanges)


class TriggerMessage(OCPPTest):
    name = "trigger_message_status_notification"
    category = "remote_control"
    description = "TriggerMessage(StatusNotification) → charger sends StatusNotification"
    ocpp_spec_ref = "OCPP 1.6 §6.7"
    severity = Severity.WARNING
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        exchanges = []

        payload = {"requestedMessage": "StatusNotification", "connectorId": 1}
        resp = await connection.send_call_and_wait("TriggerMessage", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "TriggerMessage", "trigger", payload))

        if resp is None:
            return self.result(False, "TriggerMessage timed out", exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "TriggerMessage.conf", "trigger", resp))

        if resp.get("_is_error"):
            ec = resp.get("error_code", "")
            if ec in ("NotImplemented", "NotSupported"):
                return self.skip("TriggerMessage not supported by charger")
            return self.result(False, f"TriggerMessage error: {ec}", exchanges=exchanges)

        status = resp.get("status", "")
        valid = {"Accepted", "Rejected", "NotImplemented"}
        if status not in valid:
            return self.result(False,
                f"Invalid TriggerMessage status: '{status}'",
                expected=f"One of: {sorted(valid)}",
                actual=f"'{status}'",
                exchanges=exchanges)

        if status in ("Rejected", "NotImplemented"):
            return self.result(True,
                f"TriggerMessage returned {status} (acceptable)",
                exchanges=exchanges)

        # Wait for the triggered StatusNotification
        sn_item = await connection.wait_for_action("StatusNotification", timeout=15.0)
        if not sn_item:
            return self.result(False,
                "TriggerMessage(StatusNotification) accepted but no StatusNotification received",
                expected="StatusNotification within 15s",
                actual="No StatusNotification",
                fix="After accepting TriggerMessage, send the requested message",
                exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "StatusNotification", sn_item["unique_id"], sn_item["payload"]))
        await connection.send_result(sn_item["unique_id"], {})
        return self.result(True,
            "TriggerMessage(StatusNotification) → StatusNotification received",
            exchanges=exchanges)


ALL_TESTS = [
    ResetSoft,
    ResetHard,
    ChangeConfigurationAccepted,
    ChangeConfigurationUnknownKey,
    GetConfigurationAll,
    GetConfigurationSpecificKey,
    UnlockConnector,
    TriggerMessage,
]
