"""
OCPP 2.0.1 Protocol compliance tests.
JSON-RPC structure validation, unique IDs, error handling, WebSocket subprotocol.
Same structure as v16/protocol.py but adapted for 2.0.1 subprotocol and message format.
"""
import asyncio
import json
import uuid

from tests.base import OCPPTest, TestResult, Severity, make_exchange

# OCPP 2.0.1 uses same JSON-RPC wire format as 1.6
CALL = 2
CALL_RESULT = 3
CALL_ERROR = 4

CALL_ERROR_CODES = {
    "NotImplemented", "NotSupported", "InternalError", "ProtocolError",
    "SecurityError", "FormationViolation", "PropertyConstraintViolation",
    "OccurrenceConstraintViolation", "TypeConstraintViolation", "GenericError",
}

# Valid OCPP 2.0.1 CSMS-to-Charger actions (for detecting unknown action responses)
VALID_201_CHARGER_ACTIONS = {
    "BootNotification", "Heartbeat", "StatusNotification", "Authorize",
    "TransactionEvent", "MeterValues", "SecurityEventNotification",
    "SignCertificate", "FirmwareStatusNotification", "LogStatusNotification",
    "NotifyReport", "NotifyChargingLimit", "ReportChargingProfiles",
    "NotifyEVChargingNeeds", "NotifyEVChargingSchedule",
    "NotifyDisplayMessages", "NotifyCustomerInformation", "DataTransfer",
    "PublishFirmwareStatusNotification",
}


class SubprotocolNegotiation201(OCPPTest):
    name = "protocol201_subprotocol"
    category = "protocol"
    description = "Charger negotiates 'ocpp2.0.1' WebSocket subprotocol"
    ocpp_spec_ref = "OCPP 2.0.1 §2"
    severity = Severity.CRITICAL
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        subprotocol = connection.ws.subprotocol or ""
        ocpp_version = connection.ocpp_version

        if not subprotocol:
            return self.result(False,
                "No WebSocket subprotocol negotiated",
                expected="Subprotocol: 'ocpp2.0.1'",
                actual="No subprotocol in WebSocket handshake",
                fix="Set Sec-WebSocket-Protocol header to 'ocpp2.0.1'. "
                    "Example: 'Sec-WebSocket-Protocol: ocpp2.0.1'")

        if subprotocol != "ocpp2.0.1":
            return self.result(False,
                f"Wrong subprotocol: '{subprotocol}'",
                expected="'ocpp2.0.1' (lowercase, no spaces, no extra chars)",
                actual=f"'{subprotocol}'",
                fix="Use exactly 'ocpp2.0.1' as the Sec-WebSocket-Protocol value")

        return self.result(True,
            f"Subprotocol correctly negotiated: '{subprotocol}'",
            details={"subprotocol": subprotocol, "ocpp_version": ocpp_version})


class MessageJsonStructure201(OCPPTest):
    name = "protocol201_json_structure"
    category = "protocol"
    description = "All messages from charger are valid JSON arrays [MessageTypeId, UniqueId, ...]"
    ocpp_spec_ref = "OCPP 2.0.1 §2"
    severity = Severity.CRITICAL
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        log_entries = connection.log.get_all()
        inbound = [e for e in log_entries if e["direction"] == "IN"]

        if not inbound:
            return self.skip("No messages received yet")

        violations = []
        for e in inbound:
            raw = e.get("raw", "")
            parsed = e.get("parsed")

            if parsed is None:
                violations.append(f"Invalid JSON: {raw[:100]!r}")
                continue
            if not isinstance(parsed, list):
                violations.append(f"Not a JSON array: {raw[:100]!r}")
                continue
            if len(parsed) < 3:
                violations.append(f"Array too short (len={len(parsed)}): {raw[:100]!r}")
                continue

            msg_type = parsed[0]
            if msg_type not in (2, 3, 4):
                violations.append(f"Invalid MessageTypeId={msg_type}: {raw[:100]!r}")
                continue

            if msg_type == 2:
                if len(parsed) < 4:
                    violations.append(f"CALL too short: {raw[:100]!r}")
                elif not isinstance(parsed[1], str):
                    violations.append(f"CALL uniqueId not string: {raw[:100]!r}")
                elif not isinstance(parsed[2], str):
                    violations.append(f"CALL action not string: {raw[:100]!r}")
                elif not isinstance(parsed[3], dict):
                    violations.append(f"CALL payload not object: {raw[:100]!r}")
            elif msg_type == 3:
                if not isinstance(parsed[1], str):
                    violations.append(f"CALL_RESULT uniqueId not string: {raw[:100]!r}")
            elif msg_type == 4:
                if len(parsed) < 5:
                    violations.append(f"CALL_ERROR too short: {raw[:100]!r}")
                elif not isinstance(parsed[2], str):
                    violations.append(f"CALL_ERROR errorCode not string: {raw[:100]!r}")

        if violations:
            return self.result(False,
                f"{len(violations)} JSON structure violation(s)",
                expected="All messages: [MessageTypeId, UniqueId, ...]",
                actual=f"First: {violations[0]}",
                fix="Ensure all OCPP messages are valid JSON arrays. "
                    "CALL: [2, uid, action, {}]  CALL_RESULT: [3, uid, {}]  "
                    "CALL_ERROR: [4, uid, errorCode, description, {}]",
                details={"violations": violations[:10]})

        return self.result(True,
            f"All {len(inbound)} inbound messages have valid JSON-RPC structure")


class UniqueIdFormat201(OCPPTest):
    name = "protocol201_unique_id_format"
    category = "protocol"
    description = "CALL uniqueIds are unique strings, max 36 chars"
    ocpp_spec_ref = "OCPP 2.0.1 §2"
    severity = Severity.CRITICAL
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        log_entries = connection.log.get_all()
        violations = []
        duplicates = []
        seen_ids: set = set()

        for e in log_entries:
            parsed = e.get("parsed")
            if parsed and isinstance(parsed, list) and parsed[0] == 2 and e["direction"] == "IN":
                uid = parsed[1] if len(parsed) > 1 else None
                if uid is None:
                    violations.append("CALL with no uniqueId")
                    continue
                if not isinstance(uid, str):
                    violations.append(f"uniqueId not string: {uid!r}")
                    continue
                if len(uid) > 36:
                    violations.append(f"uniqueId too long: {uid!r} ({len(uid)} > 36 chars)")
                if not uid:
                    violations.append("uniqueId is empty string")
                if uid in seen_ids:
                    duplicates.append(f"Duplicate uniqueId: '{uid}'")
                seen_ids.add(uid)

        all_issues = violations + duplicates
        if all_issues:
            return self.result(False,
                f"UniqueId violations: {'; '.join(all_issues[:5])}",
                expected="UniqueId: unique string, max 36 chars",
                actual="; ".join(all_issues[:5]),
                fix="Use UUIDs (max 36 chars). Never reuse a uniqueId within a session.",
                details={"violations": violations[:10], "duplicates": duplicates[:10]})

        return self.result(True,
            f"All {len(seen_ids)} uniqueIds valid and unique")


class UnknownMessageHandling201(OCPPTest):
    name = "protocol201_unknown_message"
    category = "protocol"
    description = "Charger responds with CallError (NotImplemented) for unknown CSMS actions"
    ocpp_spec_ref = "OCPP 2.0.1 §2.1"
    severity = Severity.CRITICAL
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        exchanges = []
        fake_payload = {"reason": "testing_unknown_action_ocpp201"}
        uid = str(uuid.uuid4())
        msg = json.dumps([2, uid, "FakeAction_NonExistent_201", fake_payload])
        connection.log.log("OUT", msg, connection.charger_id)
        await connection.ws.send(msg)
        exchanges.append(make_exchange("SENT", "FakeAction_NonExistent_201", uid, fake_payload))

        fut = asyncio.get_event_loop().create_future()
        connection._pending_results[uid] = fut
        try:
            resp = await asyncio.wait_for(asyncio.shield(fut), timeout=10.0)
        except asyncio.TimeoutError:
            connection._pending_results.pop(uid, None)
            return self.result(False,
                "No response to unknown action (timeout after 10s)",
                expected="CALL_ERROR with NotImplemented or NotSupported",
                actual="No response",
                fix="Respond to unknown actions with CALL_ERROR [4, uid, 'NotImplemented', '', {}]",
                exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "Response", uid, resp))

        if resp.get("_is_error"):
            error_code = resp.get("error_code", "")
            if error_code in ("NotImplemented", "NotSupported", "GenericError"):
                return self.result(True,
                    f"Unknown action correctly returned CallError: {error_code}",
                    exchanges=exchanges)
            elif error_code in CALL_ERROR_CODES:
                return self.result(True,
                    f"Unknown action returned CallError: {error_code} (valid, NotImplemented preferred)",
                    exchanges=exchanges)
            else:
                return self.result(False,
                    f"Non-standard error code for unknown action: '{error_code}'",
                    expected="NotImplemented or NotSupported",
                    actual=f"'{error_code}'",
                    fix=f"Use standard OCPP error code. Valid codes: {sorted(CALL_ERROR_CODES)}",
                    exchanges=exchanges)

        return self.result(False,
            "Unknown action returned CALL_RESULT instead of CALL_ERROR",
            expected="CALL_ERROR [4, uid, 'NotImplemented', ...]",
            actual=f"CALL_RESULT: {resp}",
            fix="Unknown actions must return CALL_ERROR, not CALL_RESULT",
            exchanges=exchanges)


class MalformedJsonHandling201(OCPPTest):
    name = "protocol201_malformed_json"
    category = "protocol"
    description = "Charger handles malformed JSON gracefully (stays connected)"
    ocpp_spec_ref = "OCPP 2.0.1 §2"
    severity = Severity.CRITICAL
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        exchanges = []
        broken = '{"broken": json without closing'
        connection.log.log("OUT", broken, connection.charger_id)
        await connection.ws.send(broken)
        exchanges.append(make_exchange("SENT", "MALFORMED_JSON", "malformed201", broken))

        await asyncio.sleep(1.0)

        if not connection.is_connected:
            return self.result(False,
                "Charger disconnected after receiving malformed JSON",
                expected="Charger stays connected and continues normal operation",
                actual="WebSocket connection closed",
                fix="Malformed JSON must not crash the charger. Log the error and continue.",
                exchanges=exchanges)

        # Verify still responsive with a valid message
        resp = await connection.send_call_and_wait("GetVariables", {
            "getVariableData": [
                {"component": {"name": "OCPPCommCtrlr"}, "variable": {"name": "HeartbeatInterval"}}
            ]
        }, timeout=10.0)

        if resp is None:
            return self.result(False,
                "Charger not responsive after malformed JSON",
                expected="Charger fully functional after invalid message",
                actual="No response to GetVariables",
                fix="Malformed JSON must not affect charger operation",
                exchanges=exchanges)

        return self.result(True,
            "Charger handled malformed JSON gracefully and remains responsive",
            exchanges=exchanges)


class NoConcurrentCalls201(OCPPTest):
    name = "protocol201_no_concurrent_calls"
    category = "protocol"
    description = "Charger does not send concurrent CALL messages (waits for response)"
    ocpp_spec_ref = "OCPP 2.0.1 §2.2"
    severity = Severity.WARNING
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        log_entries = connection.log.get_all()
        pending: dict[str, float] = {}
        violations = []

        for e in log_entries:
            parsed = e.get("parsed")
            if not parsed or not isinstance(parsed, list):
                continue

            if e["direction"] == "IN" and parsed[0] == 2:
                uid = parsed[1]
                action = parsed[2] if len(parsed) > 2 else "?"
                if pending:
                    existing = list(pending.keys())
                    violations.append(
                        f"CALL({action}, uid={uid[:8]}) sent while {existing[0][:8]} still pending"
                    )
                pending[uid] = e["ts_mono"]
            elif e["direction"] == "OUT" and parsed[0] == 3:
                uid = parsed[1]
                pending.pop(uid, None)

        if violations:
            return self.result(False,
                f"Concurrent CALL violations: {'; '.join(violations[:3])}",
                expected="One CALL at a time — wait for CALL_RESULT before sending next CALL",
                actual="; ".join(violations[:3]),
                fix="Implement a message queue: send one CALL, wait for response, then send next.",
                details={"violations": violations[:10]})

        return self.result(True, "No concurrent CALL violations detected")


class MessageTypesUsed201(OCPPTest):
    name = "protocol201_message_types"
    category = "protocol"
    description = "Charger only sends valid MessageTypeIds (2=CALL, 3=CALL_RESULT, 4=CALL_ERROR)"
    ocpp_spec_ref = "OCPP 2.0.1 §2"
    severity = Severity.CRITICAL
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        log_entries = connection.log.get_all()
        inbound = [e for e in log_entries if e["direction"] == "IN"]

        violations = []
        for e in inbound:
            parsed = e.get("parsed")
            if parsed and isinstance(parsed, list):
                msg_type = parsed[0]
                if msg_type not in (2, 3, 4):
                    violations.append(f"Unknown MessageTypeId={msg_type}")

        if violations:
            return self.result(False,
                "; ".join(violations[:5]),
                expected="MessageTypeId ∈ {2, 3, 4}",
                actual="; ".join(violations[:5]),
                fix="Only use MessageTypeId 2 (CALL), 3 (CALL_RESULT), or 4 (CALL_ERROR)")

        type_counts: dict = {}
        for e in inbound:
            parsed = e.get("parsed")
            if parsed and isinstance(parsed, list):
                t = parsed[0]
                type_counts[t] = type_counts.get(t, 0) + 1

        return self.result(True,
            f"All messages use valid MessageTypeIds: "
            + ", ".join(f"type{t}={count}" for t, count in sorted(type_counts.items())),
            details={"type_counts": type_counts})


ALL_TESTS = [
    SubprotocolNegotiation201,
    MessageJsonStructure201,
    UniqueIdFormat201,
    UnknownMessageHandling201,
    MalformedJsonHandling201,
    NoConcurrentCalls201,
    MessageTypesUsed201,
]
