"""
OCPP 2.0.1 Variable management tests.
SetVariables / GetVariables replace 1.6 ChangeConfiguration / GetConfiguration.
"""
import asyncio
import time

from tests.base import OCPPTest, TestResult, Severity, make_exchange
from ocpp_messages.v201 import (
    set_variables_conf, get_variables_conf,
    SET_VARIABLE_STATUS, GET_VARIABLE_STATUS
)


class GetVariables201(OCPPTest):
    name = "get_variables_201"
    category = "remote_control"
    description = "GetVariables returns variable values with valid status codes"
    ocpp_spec_ref = "OCPP 2.0.1 §6.7"
    severity = Severity.WARNING
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        exchanges = []
        # Request HeartbeatInterval from Core component
        payload = {
            "getVariableData": [
                {
                    "component": {"name": "OCPPCommCtrlr"},
                    "variable": {"name": "HeartbeatInterval"},
                }
            ]
        }
        resp = await connection.send_call_and_wait("GetVariables", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "GetVariables", "gv_201", payload))

        if resp is None:
            return self.result(False, "GetVariables timed out", exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "GetVariables.conf", "gv_201", resp))

        if resp.get("_is_error"):
            ec = resp.get("error_code", "")
            if ec in ("NotImplemented", "NotSupported"):
                return self.skip("GetVariables not supported")
            return self.result(False, f"GetVariables error: {ec}", exchanges=exchanges)

        results = resp.get("getVariableResult", [])
        if not isinstance(results, list):
            return self.result(False,
                "getVariableResult is not an array",
                exchanges=exchanges)

        issues = []
        for item in results:
            if not isinstance(item, dict):
                issues.append(f"Result item not object: {item!r}")
                continue
            status = item.get("attributeStatus", "")
            if status not in GET_VARIABLE_STATUS:
                issues.append(f"Invalid attributeStatus: '{status}'")

        if issues:
            return self.result(False, "; ".join(issues[:5]),
                fix=f"Use valid status codes: {sorted(GET_VARIABLE_STATUS)}",
                exchanges=exchanges)

        return self.result(True,
            f"GetVariables returned {len(results)} result(s)",
            exchanges=exchanges,
            details={"results": results})


class SetVariables201(OCPPTest):
    name = "set_variables_201"
    category = "remote_control"
    description = "SetVariables responds with valid status codes"
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
        exchanges.append(make_exchange("SENT", "SetVariables", "sv_201", payload))

        if resp is None:
            return self.result(False, "SetVariables timed out", exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "SetVariables.conf", "sv_201", resp))

        if resp.get("_is_error"):
            ec = resp.get("error_code", "")
            if ec in ("NotImplemented", "NotSupported"):
                return self.skip("SetVariables not supported")
            return self.result(False, f"SetVariables error: {ec}", exchanges=exchanges)

        results = resp.get("setVariableResult", [])
        issues = []
        for item in results:
            if isinstance(item, dict):
                status = item.get("attributeStatus", "")
                if status not in SET_VARIABLE_STATUS:
                    issues.append(f"Invalid attributeStatus: '{status}'")

        if issues:
            return self.result(False, "; ".join(issues[:5]),
                fix=f"Valid attributeStatus values: {sorted(SET_VARIABLE_STATUS)}",
                exchanges=exchanges)

        return self.result(True,
            f"SetVariables returned {len(results)} result(s)",
            exchanges=exchanges)


ALL_TESTS = [
    GetVariables201,
    SetVariables201,
]
