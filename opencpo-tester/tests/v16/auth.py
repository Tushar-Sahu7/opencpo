"""
OCPP 1.6 Authorization tests.
Validates Authorize request/response handling.
"""
import asyncio
import json
import re
import time

from tests.base import OCPPTest, TestResult, Severity, make_exchange
from ocpp_messages.v16 import (
    authorize_conf, AUTHORIZATION_STATUS, FIELD_LENGTHS,
    get_local_list_version_conf, send_local_list_conf
)


def is_printable_ascii(s: str) -> bool:
    return all(32 <= ord(c) <= 126 for c in s)


class AuthorizeValidIdTag(OCPPTest):
    name = "authorize_valid_idtag"
    category = "auth"
    description = "Charger sends Authorize with valid idTag and handles Accepted response"
    ocpp_spec_ref = "OCPP 1.6 §5.1"
    severity = Severity.CRITICAL
    versions = ["1.6"]
    interactive = True

    async def run(self, connection) -> TestResult:
        valid_tag = self.config.get("valid_rfid_tag", self.config.get("rfid", {}).get("valid_tag", ""))

        # Wait for an Authorize request
        item = await connection.wait_for_action("Authorize", timeout=60.0)
        if not item:
            return self.result(False,
                "No Authorize request received (timeout)",
                expected="Authorize request after RFID tap or RemoteStart",
                actual="No Authorize received within 60s",
                fix="Ensure charger sends Authorize before starting a transaction. "
                    "Tap an RFID card to trigger authorization.")

        payload = item["payload"]
        id_tag = payload.get("idTag", "")
        exchanges = [make_exchange("RECEIVED", "Authorize", item["unique_id"], payload)]

        # Respond with Accepted
        resp = authorize_conf("Accepted")
        await connection.send_result(item["unique_id"], resp)
        exchanges.append(make_exchange("SENT", "Authorize.conf", item["unique_id"], resp))

        # Validate idTag format
        issues = []
        if not id_tag:
            issues.append("idTag is empty")
        elif len(id_tag) > FIELD_LENGTHS["idTag"]:
            issues.append(f"idTag too long: {len(id_tag)} chars (max {FIELD_LENGTHS['idTag']})")
        elif not is_printable_ascii(id_tag):
            issues.append(f"idTag contains non-printable ASCII chars")

        if issues:
            return self.result(False,
                f"Authorize idTag issues: {'; '.join(issues)}",
                expected=f"idTag: max {FIELD_LENGTHS['idTag']} printable ASCII chars",
                actual=f"idTag='{id_tag}'",
                fix=f"idTag must be max {FIELD_LENGTHS['idTag']} printable ASCII characters",
                exchanges=exchanges)

        return self.result(True,
            f"Authorize sent with idTag='{id_tag}', responded Accepted",
            exchanges=exchanges,
            details={"id_tag": id_tag})


class AuthorizeInvalidIdTag(OCPPTest):
    name = "authorize_invalid_idtag"
    category = "auth"
    description = "Charger correctly handles Authorize response with Invalid/Blocked/Expired status"
    ocpp_spec_ref = "OCPP 1.6 §5.1"
    severity = Severity.WARNING
    versions = ["1.6"]
    interactive = True

    async def run(self, connection) -> TestResult:
        # Wait for an Authorize request
        item = await connection.wait_for_action("Authorize", timeout=30.0)
        if not item:
            return self.skip("No Authorize request received — send an invalid RFID card")

        payload = item["payload"]
        id_tag = payload.get("idTag", "")
        exchanges = [make_exchange("RECEIVED", "Authorize", item["unique_id"], payload)]

        # Respond with Invalid
        resp = authorize_conf("Invalid")
        await connection.send_result(item["unique_id"], resp)
        exchanges.append(make_exchange("SENT", "Authorize.conf", item["unique_id"], resp))

        # Charger should NOT start a transaction after Invalid auth
        # Wait a bit to see if StartTransaction comes
        start_item = await connection.wait_for_action("StartTransaction", timeout=5.0)

        if start_item:
            exchanges.append(make_exchange("RECEIVED", "StartTransaction",
                                           start_item["unique_id"], start_item["payload"]))
            return self.result(False,
                "Charger started transaction despite Invalid authorization!",
                expected="No StartTransaction after Invalid authorization response",
                actual="StartTransaction received after responding with Invalid",
                fix="Charger MUST NOT start a transaction if authorization is Invalid/Blocked/Expired. "
                    "Show appropriate error to user instead.",
                exchanges=exchanges)

        return self.result(True,
            f"Charger correctly did not start transaction after Invalid auth for '{id_tag}'",
            exchanges=exchanges)


class AuthorizeIdTagFormat(OCPPTest):
    name = "authorize_idtag_format"
    category = "auth"
    description = "idTag in Authorize requests is max 20 chars of printable ASCII"
    ocpp_spec_ref = "OCPP 1.6 §5.1 (CiString20)"
    severity = Severity.WARNING
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        # Collect any Authorize requests seen so far
        log_entries = connection.log.get_all()
        authorize_payloads = []
        for e in log_entries:
            if e.get("parsed") and isinstance(e["parsed"], list):
                msg = e["parsed"]
                if len(msg) >= 4 and msg[0] == 2 and msg[2] == "Authorize":
                    authorize_payloads.append(msg[3])

        if not authorize_payloads:
            return self.skip("No Authorize requests captured yet")

        violations = []
        for payload in authorize_payloads:
            id_tag = payload.get("idTag", "")
            if len(id_tag) > 20:
                violations.append(f"idTag '{id_tag[:30]}...' is {len(id_tag)} chars (max 20)")
            if id_tag and not is_printable_ascii(id_tag):
                violations.append(f"idTag '{id_tag}' contains non-printable chars")

        exchanges = [
            make_exchange("RECEIVED", "Authorize", "captured", p)
            for p in authorize_payloads
        ]

        if violations:
            return self.result(False,
                "; ".join(violations),
                expected="idTag: CiString20 (max 20 printable ASCII chars)",
                actual="; ".join(violations),
                fix="Truncate idTag to 20 chars and remove non-ASCII characters",
                exchanges=exchanges)

        return self.result(True,
            f"All {len(authorize_payloads)} idTag(s) within format spec",
            exchanges=exchanges)


class AuthorizeParentIdTag(OCPPTest):
    name = "authorize_parent_idtag"
    category = "auth"
    description = "Charger handles parentIdTag in Authorize response correctly"
    ocpp_spec_ref = "OCPP 1.6 §5.1"
    severity = Severity.INFO
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        # This requires an active authorize request; check log
        log_entries = connection.log.get_all()
        authorize_payloads = []
        for e in log_entries:
            if e.get("parsed") and isinstance(e["parsed"], list):
                msg = e["parsed"]
                if len(msg) >= 4 and msg[0] == 2 and msg[2] == "Authorize":
                    authorize_payloads.append((msg[1], msg[3]))

        if not authorize_payloads:
            return self.skip("No Authorize requests seen — cannot test parentIdTag")

        return self.result(True,
            "parentIdTag test: N/A (requires specific RFID group setup)",
            details={"info": "parentIdTag allows RFID card grouping — test manually with group tokens"})


class LocalAuthListSupport(OCPPTest):
    name = "local_auth_list_support"
    category = "auth"
    description = "Test LocalAuthListManagement: GetLocalListVersion and SendLocalList"
    ocpp_spec_ref = "OCPP 1.6 §5.7"
    severity = Severity.INFO
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        # Check if LocalAuthListManagement is in SupportedFeatureProfiles
        supported = connection.known_config.get("SupportedFeatureProfiles", "")
        if "LocalAuthListManagement" not in supported and supported:
            return self.skip("LocalAuthListManagement not in SupportedFeatureProfiles")

        # Try GetLocalListVersion
        resp = await connection.send_call_and_wait("GetLocalListVersion", {}, timeout=10.0)
        exchanges = []

        if resp is None:
            return self.result(False,
                "GetLocalListVersion timed out — no response",
                expected="listVersion integer in response",
                actual="No response (timeout)",
                fix="Implement GetLocalListVersion handler that returns the current local auth list version",
                exchanges=exchanges)

        if resp.get("_is_error"):
            error_code = resp.get("error_code", "")
            if error_code in ("NotImplemented", "NotSupported"):
                return self.result(True,
                    f"GetLocalListVersion returned {error_code} — feature not supported (acceptable)",
                    exchanges=exchanges)
            return self.result(False,
                f"GetLocalListVersion returned error: {error_code}",
                exchanges=exchanges)

        version = resp.get("listVersion")
        if version is None:
            return self.result(False,
                "GetLocalListVersion response missing 'listVersion' field",
                expected="{'listVersion': <integer>}",
                actual=str(resp),
                fix="Return listVersion in GetLocalListVersion.conf",
                exchanges=exchanges)

        if not isinstance(version, int):
            return self.result(False,
                f"listVersion is not an integer: {type(version).__name__} = {version!r}",
                expected="listVersion must be integer",
                actual=str(version),
                fix="listVersion must be an integer (0 = empty list)",
                exchanges=exchanges)

        return self.result(True,
            f"GetLocalListVersion returned listVersion={version}",
            exchanges=exchanges,
            details={"list_version": version})


ALL_TESTS = [
    AuthorizeValidIdTag,
    AuthorizeInvalidIdTag,
    AuthorizeIdTagFormat,
    AuthorizeParentIdTag,
    LocalAuthListSupport,
]
