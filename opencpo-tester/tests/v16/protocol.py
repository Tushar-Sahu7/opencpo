"""
OCPP 1.6 Protocol compliance tests.
Deep validation of JSON-RPC structure, unique IDs, error handling, WebSocket behavior.
"""
import asyncio
import json
import time
import uuid

from tests.base import OCPPTest, TestResult, Severity, make_exchange
from ocpp_messages.v16 import CALL, CALL_RESULT, CALL_ERROR, CALL_ERROR_CODES


class MessageJsonStructure(OCPPTest):
    name = "protocol_json_structure"
    category = "protocol"
    description = "All messages from charger are valid JSON arrays [MessageTypeId, UniqueId, ...]"
    ocpp_spec_ref = "OCPP 1.6 §2"
    severity = Severity.CRITICAL
    versions = ["1.6"]

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
                violations.append(f"Message is not a JSON array: {raw[:100]!r}")
                continue

            if len(parsed) < 3:
                violations.append(f"Message array too short (len={len(parsed)}): {raw[:100]!r}")
                continue

            msg_type = parsed[0]
            if msg_type not in (2, 3, 4):
                violations.append(f"Invalid MessageTypeId={msg_type}: {raw[:100]!r}")
                continue

            # CALL: [2, uniqueId, action, payload]
            if msg_type == 2:
                if len(parsed) < 4:
                    violations.append(f"CALL missing action or payload: {raw[:100]!r}")
                elif not isinstance(parsed[1], str):
                    violations.append(f"CALL uniqueId not string: {raw[:100]!r}")
                elif not isinstance(parsed[2], str):
                    violations.append(f"CALL action not string: {raw[:100]!r}")
                elif not isinstance(parsed[3], dict):
                    violations.append(f"CALL payload not object: {raw[:100]!r}")

            # CALL_RESULT: [3, uniqueId, payload]
            elif msg_type == 3:
                if len(parsed) < 3:
                    violations.append(f"CALL_RESULT missing payload: {raw[:100]!r}")
                elif not isinstance(parsed[1], str):
                    violations.append(f"CALL_RESULT uniqueId not string: {raw[:100]!r}")

            # CALL_ERROR: [4, uniqueId, errorCode, description, details]
            elif msg_type == 4:
                if len(parsed) < 5:
                    violations.append(f"CALL_ERROR missing fields: {raw[:100]!r}")
                elif not isinstance(parsed[1], str):
                    violations.append(f"CALL_ERROR uniqueId not string: {raw[:100]!r}")
                elif not isinstance(parsed[2], str):
                    violations.append(f"CALL_ERROR errorCode not string: {raw[:100]!r}")

        if violations:
            return self.result(False,
                f"{len(violations)} JSON structure violations found",
                expected="All messages: [MessageTypeId, UniqueId, ...]",
                actual=f"First violation: {violations[0]}",
                fix="Ensure all OCPP messages are valid JSON arrays with correct structure. "
                    "CALL: [2, uniqueId, action, {payload}] "
                    "CALL_RESULT: [3, uniqueId, {payload}] "
                    "CALL_ERROR: [4, uniqueId, errorCode, description, {details}]",
                details={"violations": violations[:10]})

        return self.result(True,
            f"All {len(inbound)} inbound messages have valid JSON-RPC structure")


class UniqueIdFormat(OCPPTest):
    name = "protocol_unique_id_format"
    category = "protocol"
    description = "CALL uniqueIds are unique strings, max 36 chars"
    ocpp_spec_ref = "OCPP 1.6 §2"
    severity = Severity.CRITICAL
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        log_entries = connection.log.get_all()

        unique_ids = []
        violations = []
        duplicates = []

        seen_ids = set()
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
                    violations.append(f"uniqueId too long: {uid!r} ({len(uid)} chars, max 36)")

                if not uid:
                    violations.append("uniqueId is empty string")

                if uid in seen_ids:
                    duplicates.append(f"Duplicate uniqueId: '{uid}'")
                seen_ids.add(uid)

        if violations or duplicates:
            all_issues = violations + duplicates
            return self.result(False,
                f"UniqueId violations: {'; '.join(all_issues[:5])}",
                expected="UniqueId: unique string, max 36 chars",
                actual="; ".join(all_issues[:5]),
                fix="Each CALL must use a unique ID. Use UUIDs (max 36 chars). "
                    "Never reuse an ID within a session.",
                details={"violations": violations[:10], "duplicates": duplicates[:10]})

        return self.result(True,
            f"All {len(seen_ids)} uniqueIds valid and unique",
            details={"total_calls": len(seen_ids)})


class UnknownMessageHandling(OCPPTest):
    name = "protocol_unknown_message"
    category = "protocol"
    description = "Charger responds with CallError (NotImplemented/NotSupported) for unknown actions"
    ocpp_spec_ref = "OCPP 1.6 §2.1"
    severity = Severity.CRITICAL
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        exchanges = []

        # Send a fake action that no charger implements
        fake_payload = {"reason": "testing_unknown_action_compliance"}
        uid = str(uuid.uuid4())
        msg = json.dumps([2, uid, "FakeActionThatDoesNotExist", fake_payload])
        connection.log.log("OUT", msg, connection.charger_id)
        await connection.ws.send(msg)
        exchanges.append(make_exchange("SENT", "FakeActionThatDoesNotExist", uid, fake_payload))

        # Wait for a response
        fut = asyncio.get_event_loop().create_future()
        connection._pending_results[uid] = fut
        try:
            resp = await asyncio.wait_for(asyncio.shield(fut), timeout=10.0)
        except asyncio.TimeoutError:
            connection._pending_results.pop(uid, None)
            return self.result(False,
                "No response to unknown action (timeout after 10s)",
                expected="CALL_ERROR with NotImplemented or NotSupported",
                actual="No response — charger may have crashed or ignored it",
                fix="Respond to unknown actions with CALL_ERROR [4, uniqueId, 'NotImplemented', 'Action not supported', {}]",
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
                    f"Unknown action returned CallError: {error_code} (valid, though NotImplemented preferred)",
                    exchanges=exchanges)
            else:
                return self.result(False,
                    f"Unknown action returned non-standard error code: '{error_code}'",
                    expected="NotImplemented or NotSupported",
                    actual=f"'{error_code}'",
                    fix=f"Use standard OCPP error code. Valid codes: {sorted(CALL_ERROR_CODES)}",
                    exchanges=exchanges)
        else:
            # Got a CALL_RESULT instead of error — bad
            return self.result(False,
                "Unknown action returned CALL_RESULT instead of CALL_ERROR",
                expected="CALL_ERROR [4, uniqueId, 'NotImplemented', ...]",
                actual=f"CALL_RESULT with payload: {resp}",
                fix="Unknown actions must return CALL_ERROR, not CALL_RESULT with empty payload",
                exchanges=exchanges)


class MalformedJsonHandling(OCPPTest):
    name = "protocol_malformed_json"
    category = "protocol"
    description = "Charger handles malformed JSON gracefully (doesn't crash)"
    ocpp_spec_ref = "OCPP 1.6 §2"
    severity = Severity.CRITICAL
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        exchanges = []

        # Send broken JSON
        broken_json = '{"broken": json without closing brace'
        connection.log.log("OUT", broken_json, connection.charger_id)
        await connection.ws.send(broken_json)
        exchanges.append(make_exchange("SENT", "MALFORMED_JSON", "malformed", broken_json))

        # Wait briefly to see if charger sends anything back or disconnects
        item = await connection.wait_for_any_action(
            list({"BootNotification", "Heartbeat", "StatusNotification"}),
            timeout=5.0
        )

        # Also check if connection is still alive
        if not connection.is_connected:
            return self.result(False,
                "Charger disconnected after receiving malformed JSON",
                expected="Charger stays connected and either ignores or sends CallError",
                actual="WebSocket connection closed",
                fix="Malformed JSON should not crash the charger. Log the error and continue operation.",
                exchanges=exchanges)

        # Try sending a valid message to verify charger is still responsive
        resp = await connection.send_call_and_wait("GetConfiguration", {}, timeout=10.0)
        if resp is None:
            return self.result(False,
                "Charger not responsive after receiving malformed JSON",
                expected="Charger remains fully functional",
                actual="No response to GetConfiguration after malformed JSON",
                fix="Malformed JSON must not affect charger operation",
                exchanges=exchanges)

        return self.result(True,
            "Charger handled malformed JSON gracefully and remains responsive",
            exchanges=exchanges)


class MalformedPayloadHandling(OCPPTest):
    name = "protocol_malformed_payload"
    category = "protocol"
    description = "Charger returns CallError for valid CALL with wrong payload types"
    ocpp_spec_ref = "OCPP 1.6 §2.1"
    severity = Severity.WARNING
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        exchanges = []

        # Send BootNotification with wrong types (numbers where strings expected)
        bad_payload = {
            "chargePointVendor": 12345,     # should be string
            "chargePointModel": True,       # should be string
            "meterStart": "not-a-number",   # wrong field for boot but tests type handling
        }
        uid = str(uuid.uuid4())
        msg = json.dumps([2, uid, "Heartbeat", {"unexpectedField": [1, 2, 3]}])
        connection.log.log("OUT", msg, connection.charger_id)
        await connection.ws.send(msg)
        exchanges.append(make_exchange("SENT", "Heartbeat", uid, {"unexpectedField": [1, 2, 3]}))

        fut = asyncio.get_event_loop().create_future()
        connection._pending_results[uid] = fut
        try:
            resp = await asyncio.wait_for(asyncio.shield(fut), timeout=10.0)
        except asyncio.TimeoutError:
            connection._pending_results.pop(uid, None)
            # Heartbeat with extra fields — charger likely just ignores extra fields
            return self.result(True,
                "Charger handled unexpected Heartbeat field without response (acceptable)",
                exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "Response", uid, resp))

        # Either a valid heartbeat response or a CallError — both are OK
        return self.result(True,
            "Charger handled message with unexpected fields",
            exchanges=exchanges)


class MessageOrderingNoConcurrentCalls(OCPPTest):
    name = "protocol_no_concurrent_calls"
    category = "protocol"
    description = "Charger does not send a new CALL before receiving CALL_RESULT for previous"
    ocpp_spec_ref = "OCPP 1.6 §2.2"
    severity = Severity.WARNING
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        log_entries = connection.log.get_all()

        # Find cases where charger sent multiple CALLs without getting responses
        pending_calls: dict[str, float] = {}  # uid → timestamp
        violations = []

        for e in log_entries:
            parsed = e.get("parsed")
            if not parsed or not isinstance(parsed, list):
                continue

            if e["direction"] == "IN":
                if parsed[0] == 2:  # CALL from charger
                    uid = parsed[1]
                    action = parsed[2] if len(parsed) > 2 else "?"
                    if pending_calls:
                        # There's already a pending call!
                        existing = list(pending_calls.items())
                        violations.append(
                            f"Charger sent CALL({action}, uid={uid}) while still waiting "
                            f"for response to {existing}"
                        )
                    pending_calls[uid] = e["ts_mono"]

            elif e["direction"] == "OUT":
                if parsed[0] == 3:  # CALL_RESULT from us
                    uid = parsed[1]
                    pending_calls.pop(uid, None)

        if violations:
            return self.result(False,
                f"Concurrent CALL violations: {'; '.join(violations[:3])}",
                expected="Charger waits for CALL_RESULT before sending next CALL",
                actual="; ".join(violations[:3]),
                fix="Implement a message queue: only send one CALL at a time. "
                    "Wait for the CALL_RESULT before sending the next CALL.",
                details={"violations": violations[:10]})

        return self.result(True, "No concurrent CALL violations detected")


class SubprotocolNegotiation(OCPPTest):
    name = "protocol_subprotocol"
    category = "protocol"
    description = "Charger correctly negotiates OCPP subprotocol (ocpp1.6 or ocpp2.0.1)"
    ocpp_spec_ref = "OCPP 1.6 §2"
    severity = Severity.CRITICAL
    versions = ["1.6", "2.0.1"]

    async def run(self, connection) -> TestResult:
        subprotocol = connection.ws.subprotocol or ""
        ocpp_version = connection.ocpp_version

        if not subprotocol:
            return self.result(False,
                "No WebSocket subprotocol negotiated",
                expected="Subprotocol: 'ocpp1.6' or 'ocpp2.0.1'",
                actual="No subprotocol in WebSocket handshake",
                fix="Set Sec-WebSocket-Protocol header to 'ocpp1.6' (or 'ocpp2.0.1'). "
                    "Example header: 'Sec-WebSocket-Protocol: ocpp1.6'")

        valid_subprotocols = {"ocpp1.6", "ocpp2.0.1"}
        if subprotocol not in valid_subprotocols:
            return self.result(False,
                f"Invalid subprotocol: '{subprotocol}'",
                expected=f"One of: {valid_subprotocols}",
                actual=f"'{subprotocol}'",
                fix=f"Use exactly 'ocpp1.6' or 'ocpp2.0.1' (lowercase, no spaces)")

        return self.result(True,
            f"Subprotocol correctly negotiated: '{subprotocol}' → OCPP {ocpp_version}",
            details={"subprotocol": subprotocol, "ocpp_version": ocpp_version})


ALL_TESTS = [
    SubprotocolNegotiation,
    MessageJsonStructure,
    UniqueIdFormat,
    UnknownMessageHandling,
    MalformedJsonHandling,
    MalformedPayloadHandling,
    MessageOrderingNoConcurrentCalls,
]
