"""
OCPP 2.0.1 Security tests.
SecurityEventNotification and SignCertificate are part of the Security Profile.
These tests verify proper security event reporting and certificate signing flows.
"""
import asyncio

from tests.base import OCPPTest, TestResult, Severity, make_exchange
from ocpp_messages.v201 import SECURITY_EVENTS, CERTIFICATE_TYPES

# Valid criticalityTypes for SecurityEventNotification (from OCPP 2.0.1 Part 2)
SECURITY_EVENT_CRITICALITY = {"Critical", "Informational"}


class SecurityEventNotification201(OCPPTest):
    name = "security_event_notification_201"
    category = "security"
    description = "SecurityEventNotification messages have required fields and valid type values"
    ocpp_spec_ref = "OCPP 2.0.1 §10.5"
    severity = Severity.WARNING
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        # Collect any SecurityEventNotification messages from log
        log_entries = connection.log.get_all()
        sec_events = []
        for e in log_entries:
            if e.get("parsed") and isinstance(e["parsed"], list):
                msg = e["parsed"]
                if msg[0] == 2 and msg[2] == "SecurityEventNotification":
                    sec_events.append({"uid": msg[1], "payload": msg[3]})

        if not sec_events:
            return self.result(True,
                "No SecurityEventNotification messages received (optional unless security profile active)",
                details={"note": "Security events are only triggered by specific conditions"})

        issues = []
        exchanges = []
        for sev in sec_events:
            payload = sev["payload"]
            exchanges.append(make_exchange("RECEIVED", "SecurityEventNotification", sev["uid"], payload))

            # Required fields
            if not payload.get("type"):
                issues.append("Missing 'type' field")
            elif payload["type"] not in SECURITY_EVENTS:
                issues.append(f"Unknown security event type: '{payload['type']}'")

            if not payload.get("timestamp"):
                issues.append("Missing 'timestamp' field")

            # Optional but common
            techInfo = payload.get("techInfo", "")
            if techInfo and len(techInfo) > 500:
                issues.append(f"techInfo too long: {len(techInfo)} chars (max 500)")

        if issues:
            unique = list(dict.fromkeys(issues))[:5]
            return self.result(False,
                "; ".join(unique),
                expected="SecurityEventNotification: {type, timestamp, [techInfo]}",
                actual="; ".join(unique),
                fix="Ensure SecurityEventNotification includes 'type' (from OCPP spec enum) and 'timestamp'",
                exchanges=exchanges,
                details={"valid_types": sorted(SECURITY_EVENTS)})

        event_types = [sev["payload"].get("type") for sev in sec_events]
        return self.result(True,
            f"SecurityEventNotification valid: {len(sec_events)} event(s) — types: {event_types}",
            exchanges=exchanges)


class SignCertificate201(OCPPTest):
    name = "sign_certificate_201"
    category = "security"
    description = "SignCertificate request from charger has valid CSR and certificate type"
    ocpp_spec_ref = "OCPP 2.0.1 §10.7"
    severity = Severity.INFO
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        # Collect any SignCertificate requests from log
        log_entries = connection.log.get_all()
        sign_requests = []
        for e in log_entries:
            if e.get("parsed") and isinstance(e["parsed"], list):
                msg = e["parsed"]
                if msg[0] == 2 and msg[2] == "SignCertificate":
                    sign_requests.append({"uid": msg[1], "payload": msg[3]})

        if not sign_requests:
            return self.result(True,
                "No SignCertificate requests received (requires TLS security profile active)",
                details={"note": "SignCertificate is only triggered with Security Profile 3 (mutual TLS)"})

        issues = []
        exchanges = []
        for req in sign_requests:
            payload = req["payload"]
            exchanges.append(make_exchange("RECEIVED", "SignCertificate", req["uid"], payload))

            csr = payload.get("csr", "")
            cert_type = payload.get("certificateType")

            if not csr:
                issues.append("Missing 'csr' field")
            elif "BEGIN CERTIFICATE REQUEST" not in csr and "BEGIN NEW CERTIFICATE REQUEST" not in csr:
                issues.append(f"csr does not appear to be a valid PEM CSR")

            if cert_type and cert_type not in CERTIFICATE_TYPES:
                issues.append(f"Invalid certificateType: '{cert_type}'")

        if issues:
            unique = list(dict.fromkeys(issues))[:5]
            return self.result(False,
                "; ".join(unique),
                expected="SignCertificate: {csr: PEM string, [certificateType]}",
                actual="; ".join(unique),
                fix="CSR must be a valid PEM-encoded certificate signing request. "
                    f"certificateType must be one of: {sorted(CERTIFICATE_TYPES)}",
                exchanges=exchanges)

        return self.result(True,
            f"SignCertificate request(s) valid: {len(sign_requests)} CSR(s)",
            exchanges=exchanges)


class SecurityProfile201Awareness(OCPPTest):
    name = "security_profile_201_awareness"
    category = "security"
    description = "Charger reports SecurityCtrlr variables indicating active security profile"
    ocpp_spec_ref = "OCPP 2.0.1 §10.1"
    severity = Severity.INFO
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        # Try to get security profile level via GetVariables
        resp = await connection.send_call_and_wait("GetVariables", {
            "getVariableData": [
                {
                    "component": {"name": "SecurityCtrlr"},
                    "variable": {"name": "SecurityProfile"},
                }
            ]
        }, timeout=10.0)

        if resp is None:
            return self.result(True,
                "GetVariables timed out — cannot determine security profile (OK)",
                details={"note": "SecurityCtrlr.SecurityProfile query failed"})

        results = resp.get("getVariableResult", [])
        if not results:
            return self.result(True,
                "SecurityCtrlr.SecurityProfile not returned",
                details={"note": "Charger may not support SecurityCtrlr component"})

        status = results[0].get("attributeStatus", "")
        value = results[0].get("attributeValue", "")

        if status in ("UnknownComponent", "UnknownVariable"):
            return self.result(True,
                f"SecurityCtrlr not present ({status}) — Security Profile 1 assumed",
                details={"note": "Security Profile 1 uses basic auth only"})

        if status == "Accepted":
            try:
                profile_num = int(value)
                labels = {1: "HTTP basic auth", 2: "TLS + CA cert", 3: "Mutual TLS"}
                label = labels.get(profile_num, "unknown")
                return self.result(True,
                    f"SecurityProfile = {profile_num} ({label})",
                    details={"security_profile": profile_num, "description": label})
            except (ValueError, TypeError):
                pass

        return self.result(True,
            f"SecurityCtrlr.SecurityProfile = '{value}' (status={status})",
            details={"status": status, "value": value})


ALL_TESTS = [
    SecurityEventNotification201,
    SignCertificate201,
    SecurityProfile201Awareness,
]
