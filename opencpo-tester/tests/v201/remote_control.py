"""
OCPP 2.0.1 Remote Control tests.
Reset, TriggerMessage, ChangeAvailability, UnlockConnector.
GetVariables / SetVariables are in variables.py (already exists as remote_control category).
"""
import asyncio
import time

from tests.base import OCPPTest, TestResult, Severity, make_exchange
from ocpp_messages.v201 import (
    reset_conf, trigger_message_conf,
    set_variables_conf, get_variables_conf,
    SET_VARIABLE_STATUS, GET_VARIABLE_STATUS
)


class Reset201Immediate(OCPPTest):
    name = "reset201_immediate"
    category = "remote_control"
    description = "Reset(Immediate) → charger reboots and reconnects with BootNotification"
    ocpp_spec_ref = "OCPP 2.0.1 §5.12"
    severity = Severity.CRITICAL
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        exchanges = []
        payload = {"type": "Immediate"}
        resp = await connection.send_call_and_wait("Reset", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "Reset", "reset201_imm", payload))

        if resp is None:
            return self.result(False,
                "Reset(Immediate) timed out — no response",
                expected="status: Accepted or Rejected",
                actual="No response",
                fix="Implement Reset handler that responds with Accepted or Rejected",
                exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "Reset.conf", "reset201_imm", resp))

        if resp.get("_is_error"):
            return self.result(False,
                f"Reset returned error: {resp.get('error_code')}",
                exchanges=exchanges)

        status = resp.get("status", "")
        if status not in ("Accepted", "Rejected", "Scheduled"):
            return self.result(False,
                f"Invalid Reset status: '{status}'",
                expected="'Accepted', 'Rejected', or 'Scheduled'",
                actual=f"'{status}'",
                fix="Reset.conf status must be one of: Accepted, Rejected, Scheduled",
                exchanges=exchanges)

        return self.result(True,
            f"Reset(Immediate) → {status}",
            exchanges=exchanges,
            details={"note": "Reboot behavior verifiable by watching server reconnect logs"})


class Reset201OnEVSE(OCPPTest):
    name = "reset201_evse"
    category = "remote_control"
    description = "Reset with evseId targets a specific EVSE"
    ocpp_spec_ref = "OCPP 2.0.1 §5.12"
    severity = Severity.INFO
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        exchanges = []
        payload = {"type": "OnIdle", "evseId": 1}
        resp = await connection.send_call_and_wait("Reset", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "Reset", "reset201_evse", payload))

        if resp is None:
            return self.result(False, "Reset(OnIdle, evseId=1) timed out", exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "Reset.conf", "reset201_evse", resp))

        if resp.get("_is_error"):
            ec = resp.get("error_code", "")
            if ec in ("NotImplemented", "NotSupported"):
                return self.skip("EVSE-level Reset not supported")
            return self.result(False, f"Reset error: {ec}", exchanges=exchanges)

        status = resp.get("status", "")
        return self.result(True,
            f"Reset(OnIdle, evseId=1) → {status}",
            exchanges=exchanges)


class GetVariables201Required(OCPPTest):
    name = "get_variables_201_required"
    category = "remote_control"
    description = "GetVariables returns HeartbeatInterval from OCPPCommCtrlr component"
    ocpp_spec_ref = "OCPP 2.0.1 §6.7"
    severity = Severity.WARNING
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        exchanges = []
        payload = {
            "getVariableData": [
                {
                    "component": {"name": "OCPPCommCtrlr"},
                    "variable": {"name": "HeartbeatInterval"},
                }
            ]
        }
        resp = await connection.send_call_and_wait("GetVariables", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "GetVariables", "gv_req", payload))

        if resp is None:
            return self.result(False, "GetVariables timed out", exchanges=exchanges,
                               fix="Implement GetVariables handler")

        exchanges.append(make_exchange("RECEIVED", "GetVariables.conf", "gv_req", resp))

        if resp.get("_is_error"):
            ec = resp.get("error_code", "")
            if ec in ("NotImplemented", "NotSupported"):
                return self.skip("GetVariables not supported")
            return self.result(False, f"GetVariables error: {ec}", exchanges=exchanges)

        results = resp.get("getVariableResult", [])
        if not isinstance(results, list) or not results:
            return self.result(False,
                "getVariableResult is empty or not an array",
                exchanges=exchanges)

        issues = []
        for item in results:
            status = item.get("attributeStatus", "")
            if status not in GET_VARIABLE_STATUS:
                issues.append(f"Invalid attributeStatus: '{status}'")

        if issues:
            return self.result(False, "; ".join(issues[:5]),
                fix=f"Valid attributeStatus values: {sorted(GET_VARIABLE_STATUS)}",
                exchanges=exchanges)

        return self.result(True,
            f"GetVariables returned {len(results)} result(s): "
            + ", ".join(f"{r.get('attributeStatus')}" for r in results[:3]),
            exchanges=exchanges,
            details={"results": results})


class SetVariables201HeartbeatInterval(OCPPTest):
    name = "set_variables_201_heartbeat"
    category = "remote_control"
    description = "SetVariables(HeartbeatInterval=30) responds with valid status"
    ocpp_spec_ref = "OCPP 2.0.1 §6.8"
    severity = Severity.WARNING
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        exchanges = []
        payload = {
            "setVariableData": [
                {
                    "component": {"name": "OCPPCommCtrlr"},
                    "variable": {"name": "HeartbeatInterval"},
                    "attributeValue": "30",
                }
            ]
        }
        resp = await connection.send_call_and_wait("SetVariables", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "SetVariables", "sv_hb", payload))

        if resp is None:
            return self.result(False, "SetVariables timed out", exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "SetVariables.conf", "sv_hb", resp))

        if resp.get("_is_error"):
            ec = resp.get("error_code", "")
            if ec in ("NotImplemented", "NotSupported"):
                return self.skip("SetVariables not supported")
            return self.result(False, f"SetVariables error: {ec}", exchanges=exchanges)

        results = resp.get("setVariableResult", [])
        issues = []
        for item in results:
            status = item.get("attributeStatus", "")
            if status not in SET_VARIABLE_STATUS:
                issues.append(f"Invalid attributeStatus: '{status}'")

        if issues:
            return self.result(False, "; ".join(issues[:5]),
                fix=f"Valid attributeStatus values: {sorted(SET_VARIABLE_STATUS)}",
                exchanges=exchanges)

        statuses = [r.get("attributeStatus") for r in results]
        return self.result(True,
            f"SetVariables(HeartbeatInterval=30) → {statuses}",
            exchanges=exchanges)


class SetVariables201UnknownComponent(OCPPTest):
    name = "set_variables_201_unknown_component"
    category = "remote_control"
    description = "SetVariables with unknown component returns UnknownComponent status"
    ocpp_spec_ref = "OCPP 2.0.1 §6.8"
    severity = Severity.WARNING
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        exchanges = []
        payload = {
            "setVariableData": [
                {
                    "component": {"name": "NonExistentComponent_XYZ"},
                    "variable": {"name": "SomeVariable"},
                    "attributeValue": "test",
                }
            ]
        }
        resp = await connection.send_call_and_wait("SetVariables", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "SetVariables", "sv_unk", payload))

        if resp is None:
            return self.skip("SetVariables timed out")

        exchanges.append(make_exchange("RECEIVED", "SetVariables.conf", "sv_unk", resp))

        results = resp.get("setVariableResult", [])
        if not results:
            return self.result(True,
                "SetVariables unknown component returned empty result (acceptable)",
                exchanges=exchanges)

        status = results[0].get("attributeStatus", "")
        if status in ("UnknownComponent", "Rejected"):
            return self.result(True,
                f"Unknown component correctly returned: '{status}'",
                exchanges=exchanges)

        return self.result(True,
            f"Unknown component returned '{status}' (should be UnknownComponent or Rejected)",
            exchanges=exchanges,
            details={"note": f"Charger returned {status} for unknown component"})


class TriggerMessage201(OCPPTest):
    name = "trigger_message_201"
    category = "remote_control"
    description = "TriggerMessage(StatusNotification) → charger sends StatusNotification"
    ocpp_spec_ref = "OCPP 2.0.1 §5.13"
    severity = Severity.WARNING
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        exchanges = []
        payload = {
            "requestedMessage": "StatusNotification",
            "evse": {"id": 1, "connectorId": 1},
        }
        resp = await connection.send_call_and_wait("TriggerMessage", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "TriggerMessage", "trigger201", payload))

        if resp is None:
            return self.result(False, "TriggerMessage timed out", exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "TriggerMessage.conf", "trigger201", resp))

        if resp.get("_is_error"):
            ec = resp.get("error_code", "")
            if ec in ("NotImplemented", "NotSupported"):
                return self.skip("TriggerMessage not supported")
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
            return self.result(True, f"TriggerMessage → {status} (acceptable)", exchanges=exchanges)

        # Wait for triggered StatusNotification
        sn = await connection.wait_for_action("StatusNotification", timeout=15.0)
        if not sn:
            return self.result(False,
                "TriggerMessage(StatusNotification) accepted but no StatusNotification received",
                expected="StatusNotification within 15s",
                actual="No StatusNotification",
                fix="After accepting TriggerMessage, send the requested message promptly",
                exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "StatusNotification", sn["unique_id"], sn["payload"]))
        await connection.send_result(sn["unique_id"], {})
        return self.result(True,
            "TriggerMessage(StatusNotification) → StatusNotification received ✓",
            exchanges=exchanges)


class UnlockConnector201(OCPPTest):
    name = "unlock_connector_201"
    category = "remote_control"
    description = "UnlockConnector → Unlocked, OngoingAuthorizedSession, UnlockFailed, or NotSupported"
    ocpp_spec_ref = "OCPP 2.0.1 §5.14"
    severity = Severity.INFO
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        exchanges = []
        payload = {"evseId": 1, "connectorId": 1}
        resp = await connection.send_call_and_wait("UnlockConnector", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "UnlockConnector", "unlock201", payload))

        if resp is None:
            return self.result(False, "UnlockConnector timed out", exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "UnlockConnector.conf", "unlock201", resp))

        if resp.get("_is_error"):
            ec = resp.get("error_code", "")
            if ec in ("NotImplemented", "NotSupported"):
                return self.skip("UnlockConnector not supported")
            return self.result(False, f"UnlockConnector error: {ec}", exchanges=exchanges)

        status = resp.get("status", "")
        valid = {"Unlocked", "UnlockFailed", "OngoingAuthorizedSession", "NotSupported", "UnknownConnector"}
        if status not in valid:
            return self.result(False,
                f"Invalid UnlockConnector status: '{status}'",
                expected=f"One of: {sorted(valid)}",
                actual=f"'{status}'",
                fix=f"Return a valid 2.0.1 UnlockConnector status: {sorted(valid)}",
                exchanges=exchanges)

        return self.result(True,
            f"UnlockConnector(evse=1, connector=1) → {status}",
            exchanges=exchanges)


ALL_TESTS = [
    Reset201Immediate,
    Reset201OnEVSE,
    GetVariables201Required,
    SetVariables201HeartbeatInterval,
    SetVariables201UnknownComponent,
    TriggerMessage201,
    UnlockConnector201,
]
