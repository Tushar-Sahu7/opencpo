"""
OCPP 1.6 Transaction tests.
Deep validation of StartTransaction, StopTransaction fields and flows.
"""
import asyncio
import json
import re
import time

from tests.base import OCPPTest, TestResult, Severity, make_exchange
from ocpp_messages.v16 import (
    start_transaction_conf, stop_transaction_conf, authorize_conf,
    remote_start_transaction_conf, remote_stop_transaction_conf,
    STOP_REASONS, FIELD_LENGTHS, AUTHORIZATION_STATUS
)

ISO8601_TZ_PATTERN = re.compile(
    r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$'
)


class StartTransactionRequiredFields(OCPPTest):
    name = "start_transaction_required_fields"
    category = "transactions"
    description = "StartTransaction contains all required fields: connectorId, idTag, meterStart, timestamp"
    ocpp_spec_ref = "OCPP 1.6 §5.4"
    severity = Severity.CRITICAL
    versions = ["1.6"]
    depends_on = ["authorize_valid_idtag"]

    async def run(self, connection) -> TestResult:
        # Wait for StartTransaction (should come after Authorize)
        item = await connection.wait_for_action("StartTransaction", timeout=30.0)
        if not item:
            return self.result(False,
                "No StartTransaction received",
                expected="StartTransaction after authorization",
                actual="No StartTransaction within 30s",
                fix="After receiving Authorize.conf(Accepted), send StartTransaction immediately")

        payload = item["payload"]
        exchanges = [make_exchange("RECEIVED", "StartTransaction", item["unique_id"], payload)]

        # Check required fields
        connector_id = payload.get("connectorId")
        id_tag = payload.get("idTag")
        meter_start = payload.get("meterStart")
        timestamp = payload.get("timestamp")

        issues = []

        if connector_id is None:
            issues.append("Missing 'connectorId'")
        elif not isinstance(connector_id, int):
            issues.append(f"connectorId must be integer, got {type(connector_id).__name__}")
        elif connector_id <= 0:
            issues.append(f"connectorId must be >0 (got {connector_id})")

        if not id_tag:
            issues.append("Missing 'idTag'")
        elif len(str(id_tag)) > FIELD_LENGTHS["idTag"]:
            issues.append(f"idTag too long: {len(id_tag)} chars (max {FIELD_LENGTHS['idTag']})")

        if meter_start is None:
            issues.append("Missing 'meterStart'")
        elif not isinstance(meter_start, (int, float)):
            issues.append(f"meterStart must be numeric, got {type(meter_start).__name__}")
        elif meter_start < 0:
            issues.append(f"meterStart must be ≥0 (got {meter_start})")
        elif not isinstance(meter_start, int):
            issues.append(f"meterStart should be integer Wh (got float {meter_start})")

        if not timestamp:
            issues.append("Missing 'timestamp'")
        elif not ISO8601_TZ_PATTERN.match(str(timestamp)):
            issues.append(f"Invalid timestamp format: '{timestamp}'")

        # Issue the transaction ID response
        txn_id = connection.active_transaction_id or 1001
        resp = start_transaction_conf(txn_id, "Accepted")
        await connection.send_result(item["unique_id"], resp)
        exchanges.append(make_exchange("SENT", "StartTransaction.conf", item["unique_id"], resp))

        # Store for subsequent tests
        if connector_id and meter_start is not None:
            connection.active_transaction_id = txn_id
            connection.active_connector_id = connector_id
            connection.meter_start = int(meter_start) if isinstance(meter_start, (int, float)) else 0

        if issues:
            return self.result(False,
                f"StartTransaction field violations: {'; '.join(issues)}",
                expected="connectorId (int >0), idTag (str max 20), meterStart (int Wh ≥0), timestamp (ISO8601+TZ)",
                actual=f"connectorId={connector_id}, idTag={id_tag!r}, meterStart={meter_start}, timestamp={timestamp!r}",
                fix="Fix StartTransaction payload: ensure all required fields are present with correct types",
                exchanges=exchanges)

        return self.result(True,
            f"StartTransaction valid: connector={connector_id} tag='{id_tag}' "
            f"meterStart={meter_start}Wh txn={txn_id}",
            exchanges=exchanges,
            details={"connector_id": connector_id, "id_tag": id_tag,
                     "meter_start": meter_start, "transaction_id": txn_id})


class StartTransactionConnectorId(OCPPTest):
    name = "start_transaction_connector_id"
    category = "transactions"
    description = "StartTransaction connectorId is a positive integer >0"
    ocpp_spec_ref = "OCPP 1.6 §5.4"
    severity = Severity.CRITICAL
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        # Check log for StartTransaction messages
        log_entries = connection.log.get_all()
        start_txns = []
        for e in log_entries:
            if e.get("parsed") and isinstance(e["parsed"], list):
                msg = e["parsed"]
                if len(msg) >= 4 and msg[0] == 2 and msg[2] == "StartTransaction":
                    start_txns.append(msg[3])

        if not start_txns:
            return self.skip("No StartTransaction messages seen yet")

        violations = []
        for payload in start_txns:
            cid = payload.get("connectorId")
            if cid is None or not isinstance(cid, int) or cid <= 0:
                violations.append(f"connectorId={cid!r} (must be positive integer)")

        if violations:
            return self.result(False,
                "; ".join(violations),
                expected="connectorId: positive integer ≥1",
                actual="; ".join(violations),
                fix="Set connectorId to the physical connector number (1, 2, ...) never 0",
                exchanges=[make_exchange("RECEIVED", "StartTransaction", "log", p) for p in start_txns])

        return self.result(True,
            f"All StartTransaction connectorIds valid",
            details={"connector_ids": [p.get("connectorId") for p in start_txns]})


class StopTransactionRequiredFields(OCPPTest):
    name = "stop_transaction_required_fields"
    category = "transactions"
    description = "StopTransaction contains required fields: transactionId, meterStop, timestamp"
    ocpp_spec_ref = "OCPP 1.6 §5.4"
    severity = Severity.CRITICAL
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        item = await connection.wait_for_action("StopTransaction", timeout=120.0)
        if not item:
            return self.skip("No StopTransaction received in test window")

        payload = item["payload"]
        exchanges = [make_exchange("RECEIVED", "StopTransaction", item["unique_id"], payload)]

        transaction_id = payload.get("transactionId")
        meter_stop = payload.get("meterStop")
        timestamp = payload.get("timestamp")
        reason = payload.get("reason", "Local")  # optional but should be present
        id_tag = payload.get("idTag")  # optional

        issues = []

        if transaction_id is None:
            issues.append("Missing 'transactionId'")
        elif not isinstance(transaction_id, int):
            issues.append(f"transactionId must be integer, got {type(transaction_id).__name__}")

        if meter_stop is None:
            issues.append("Missing 'meterStop'")
        elif not isinstance(meter_stop, (int, float)):
            issues.append(f"meterStop must be numeric, got {type(meter_stop).__name__}")
        elif meter_stop < 0:
            issues.append(f"meterStop must be ≥0 (got {meter_stop})")

        if not timestamp:
            issues.append("Missing 'timestamp'")
        elif not ISO8601_TZ_PATTERN.match(str(timestamp)):
            issues.append(f"Invalid timestamp: '{timestamp}'")

        if reason and reason not in STOP_REASONS:
            issues.append(f"Invalid reason: '{reason}' (not in OCPP spec stop reasons)")

        # Respond
        resp = stop_transaction_conf("Accepted")
        await connection.send_result(item["unique_id"], resp)
        exchanges.append(make_exchange("SENT", "StopTransaction.conf", item["unique_id"], resp))

        if issues:
            return self.result(False,
                f"StopTransaction field violations: {'; '.join(issues)}",
                expected="transactionId (int), meterStop (int Wh), timestamp (ISO8601+TZ)",
                actual=f"transactionId={transaction_id}, meterStop={meter_stop}, timestamp={timestamp!r}",
                fix="Ensure StopTransaction includes all required fields with correct types",
                exchanges=exchanges)

        return self.result(True,
            f"StopTransaction valid: txn={transaction_id} meterStop={meter_stop}Wh reason='{reason}'",
            exchanges=exchanges,
            details={"transaction_id": transaction_id, "meter_stop": meter_stop, "reason": reason})


class StopTransactionMeterStopNotDecreasing(OCPPTest):
    name = "stop_transaction_meter_stop_ge_meter_start"
    category = "transactions"
    description = "meterStop must be ≥ meterStart (energy cannot decrease)"
    ocpp_spec_ref = "OCPP 1.6 §5.4"
    severity = Severity.CRITICAL
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        log_entries = connection.log.get_all()

        start_payload = None
        stop_payload = None
        for e in log_entries:
            if e.get("parsed") and isinstance(e["parsed"], list):
                msg = e["parsed"]
                if len(msg) >= 4 and msg[0] == 2:
                    if msg[2] == "StartTransaction":
                        start_payload = msg[3]
                    elif msg[2] == "StopTransaction":
                        stop_payload = msg[3]

        if not start_payload or not stop_payload:
            return self.skip("Need both StartTransaction and StopTransaction to compare meter values")

        meter_start = start_payload.get("meterStart", 0)
        meter_stop = stop_payload.get("meterStop", 0)

        exchanges = [
            make_exchange("RECEIVED", "StartTransaction", "log", start_payload),
            make_exchange("RECEIVED", "StopTransaction", "log", stop_payload),
        ]

        try:
            m_start = float(meter_start)
            m_stop = float(meter_stop)
        except (TypeError, ValueError):
            return self.result(False,
                f"Cannot compare: meterStart={meter_start!r} meterStop={meter_stop!r}",
                exchanges=exchanges)

        if m_stop < m_start:
            delta = m_start - m_stop
            return self.result(False,
                f"CRITICAL: meterStop ({m_stop}) < meterStart ({m_start}) — energy went BACKWARDS by {delta} Wh!",
                expected=f"meterStop ≥ meterStart (≥ {m_start} Wh)",
                actual=f"meterStop = {m_stop} Wh (decreased by {delta} Wh)",
                fix="meterStop must equal or exceed meterStart. This is likely a meter register reset "
                    "or integer overflow bug. Check that the energy meter is cumulative and never resets "
                    "during a session.",
                exchanges=exchanges)

        energy_wh = m_stop - m_start
        energy_kwh = energy_wh / 1000.0

        return self.result(True,
            f"meterStop ({m_stop} Wh) ≥ meterStart ({m_start} Wh) — "
            f"session energy: {energy_wh:.0f} Wh ({energy_kwh:.3f} kWh)",
            exchanges=exchanges,
            details={"meter_start": m_start, "meter_stop": m_stop,
                     "session_wh": energy_wh, "session_kwh": round(energy_kwh, 3)})


class StopTransactionValidReason(OCPPTest):
    name = "stop_transaction_valid_reason"
    category = "transactions"
    description = "StopTransaction reason (if present) is a valid OCPP 1.6 stop reason"
    ocpp_spec_ref = "OCPP 1.6 §5.4"
    severity = Severity.WARNING
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        log_entries = connection.log.get_all()
        stop_payloads = []
        for e in log_entries:
            if e.get("parsed") and isinstance(e["parsed"], list):
                msg = e["parsed"]
                if len(msg) >= 4 and msg[0] == 2 and msg[2] == "StopTransaction":
                    stop_payloads.append(msg[3])

        if not stop_payloads:
            return self.skip("No StopTransaction messages seen")

        violations = []
        for p in stop_payloads:
            reason = p.get("reason")
            if reason and reason not in STOP_REASONS:
                violations.append(f"Invalid reason: '{reason}'")

        exchanges = [
            make_exchange("RECEIVED", "StopTransaction", "log", p)
            for p in stop_payloads
        ]

        if violations:
            return self.result(False,
                "; ".join(violations),
                expected=f"reason must be one of: {sorted(STOP_REASONS)}",
                actual="; ".join(violations),
                fix=f"Use a valid OCPP 1.6 stop reason. Most common: "
                    f"'Local' (user stopped), 'EVDisconnected' (cable pulled), "
                    f"'Remote' (server stopped), 'EmergencyStop'.",
                exchanges=exchanges)

        reasons_seen = [p.get("reason", "Local") for p in stop_payloads]
        return self.result(True,
            f"Stop reasons valid: {reasons_seen}",
            exchanges=exchanges)


class TransactionIdConsistency(OCPPTest):
    name = "transaction_id_consistency"
    category = "transactions"
    description = "Charger uses transactionId from StartTransaction.conf in StopTransaction and MeterValues"
    ocpp_spec_ref = "OCPP 1.6 §5.4"
    severity = Severity.CRITICAL
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        log_entries = connection.log.get_all()

        # Find StartTransaction responses (our CALL_RESULTs with transactionId)
        issued_txn_id = None
        start_uid = None
        stop_txn_id = None
        meter_txn_ids = []

        for e in log_entries:
            if e.get("parsed") and isinstance(e["parsed"], list):
                msg = e["parsed"]
                if msg[0] == 3:  # CALL_RESULT
                    # Our response to StartTransaction
                    if isinstance(msg[2], dict) and "transactionId" in msg[2]:
                        issued_txn_id = msg[2]["transactionId"]
                        start_uid = msg[1]
                elif msg[0] == 2:
                    if msg[2] == "StopTransaction" and len(msg) >= 4:
                        stop_txn_id = msg[3].get("transactionId")
                    elif msg[2] == "MeterValues" and len(msg) >= 4:
                        mv_tid = msg[3].get("transactionId")
                        if mv_tid is not None:
                            meter_txn_ids.append(mv_tid)

        if issued_txn_id is None:
            return self.skip("No StartTransaction response with transactionId found in log")

        issues = []
        if stop_txn_id is not None and stop_txn_id != issued_txn_id:
            issues.append(f"StopTransaction used txnId={stop_txn_id}, expected {issued_txn_id}")

        wrong_meter_ids = [tid for tid in meter_txn_ids if tid != issued_txn_id]
        if wrong_meter_ids:
            issues.append(f"MeterValues used wrong txnIds: {wrong_meter_ids}, expected {issued_txn_id}")

        if issues:
            return self.result(False,
                "; ".join(issues),
                expected=f"All messages use transactionId={issued_txn_id} from StartTransaction.conf",
                actual="; ".join(issues),
                fix="Store the transactionId from StartTransaction.conf and use it in all "
                    "subsequent MeterValues and StopTransaction messages for this session",
                details={"issued_txn_id": issued_txn_id, "stop_txn_id": stop_txn_id,
                         "meter_txn_ids": meter_txn_ids})

        return self.result(True,
            f"transactionId={issued_txn_id} used consistently in all messages",
            details={"transaction_id": issued_txn_id})


class TransactionTimingAfterAuth(OCPPTest):
    name = "transaction_timing_after_auth"
    category = "transactions"
    description = "StartTransaction sent within 5 seconds of authorization"
    ocpp_spec_ref = "OCPP 1.6 §5.4"
    severity = Severity.WARNING
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        log_entries = connection.log.get_all()

        # Find Authorize CALL_RESULT timestamps and StartTransaction CALL timestamps
        auth_result_ts = None
        start_txn_ts = None

        for e in log_entries:
            if e.get("parsed") and isinstance(e["parsed"], list):
                msg = e["parsed"]
                ts = e["ts_mono"]
                if msg[0] == 3:
                    # Our response — check if it was to an Authorize
                    if auth_result_ts is None:
                        # We need to correlate with the request...
                        # Simplified: use timestamp of any call_result
                        pass
                elif msg[0] == 2:
                    if msg[2] == "Authorize":
                        auth_result_ts = ts  # Approximate — use when we received it
                    elif msg[2] == "StartTransaction" and auth_result_ts is not None:
                        start_txn_ts = ts
                        break

        if auth_result_ts is None or start_txn_ts is None:
            return self.skip("Need both Authorize and StartTransaction in log to measure timing")

        elapsed = start_txn_ts - auth_result_ts
        max_allowed = self.config.get("transaction_start_max", 5)

        if elapsed > max_allowed:
            return self.result(False,
                f"StartTransaction came {elapsed:.1f}s after Authorize (max {max_allowed}s)",
                expected=f"StartTransaction within {max_allowed}s of Authorize response",
                actual=f"Delay: {elapsed:.1f}s",
                fix=f"Start the transaction immediately after authorization — no unnecessary delays. "
                    f"User experience degrades with long pre-charging delays.")
        elif elapsed < 0:
            return self.result(True,
                "Timing measurement inconclusive",
                details={"note": "Could not precisely measure auth→start delay"})

        return self.result(True,
            f"StartTransaction came {elapsed:.1f}s after Authorize (within {max_allowed}s limit)",
            details={"delay_s": round(elapsed, 2)})


class RemoteStartTransaction(OCPPTest):
    name = "remote_start_transaction"
    category = "transactions"
    description = "RemoteStartTransaction → charger sends StartTransaction (or rejects with reason)"
    ocpp_spec_ref = "OCPP 1.6 §5.6"
    severity = Severity.CRITICAL
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        valid_tag = self.config.get("valid_rfid_tag",
                    self.config.get("rfid", {}).get("valid_tag", ""))
        connector_id = 1

        exchanges = []

        # Send RemoteStartTransaction
        payload = {
            "connectorId": connector_id,
            "idTag": valid_tag,
        }
        resp = await connection.send_call_and_wait("RemoteStartTransaction", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "RemoteStartTransaction", "rstart", payload))

        if resp is None:
            return self.result(False,
                "RemoteStartTransaction timed out — no response",
                expected="status: Accepted or Rejected",
                actual="No response (timeout)",
                fix="Respond to RemoteStartTransaction within 30s with Accepted or Rejected")

        exchanges.append(make_exchange("RECEIVED", "RemoteStartTransaction.conf", "rstart", resp))

        status = resp.get("status", "")
        if resp.get("_is_error"):
            return self.result(False,
                f"RemoteStartTransaction returned CallError: {resp.get('error_code')}",
                exchanges=exchanges,
                fix="RemoteStartTransaction should return status Accepted/Rejected, not CallError")

        if status not in ("Accepted", "Rejected"):
            return self.result(False,
                f"Invalid status: '{status}'",
                expected="status: 'Accepted' or 'Rejected'",
                actual=f"status='{status}'",
                fix="RemoteStartTransaction.conf status must be 'Accepted' or 'Rejected'",
                exchanges=exchanges)

        if status == "Rejected":
            return self.result(True,
                f"RemoteStartTransaction rejected (status=Rejected) — "
                f"acceptable if connector not available",
                exchanges=exchanges)

        # Accepted → wait for Authorize (optional) and StartTransaction
        # Some chargers skip Authorize for remote starts
        auth_item = None
        start_item = None

        for _ in range(2):
            item = await connection.wait_for_any_action(["Authorize", "StartTransaction"], timeout=20.0)
            if item is None:
                break
            if item["action"] == "Authorize":
                auth_item = item
                await connection.send_result(item["unique_id"], authorize_conf("Accepted"))
                exchanges.append(make_exchange("RECEIVED", "Authorize", item["unique_id"], item["payload"]))
            elif item["action"] == "StartTransaction":
                start_item = item
                txn_id = (connection.active_transaction_id or 1001)
                resp2 = start_transaction_conf(txn_id, "Accepted")
                await connection.send_result(item["unique_id"], resp2)
                connection.active_transaction_id = txn_id
                connection.active_connector_id = item["payload"].get("connectorId", 1)
                connection.meter_start = item["payload"].get("meterStart", 0)
                exchanges.append(make_exchange("RECEIVED", "StartTransaction", item["unique_id"], item["payload"]))
                exchanges.append(make_exchange("SENT", "StartTransaction.conf", item["unique_id"], resp2))
                break

        if start_item is None:
            return self.result(False,
                "RemoteStartTransaction accepted but no StartTransaction received",
                expected="StartTransaction after RemoteStartTransaction(Accepted)",
                actual="No StartTransaction within 20s",
                fix="After accepting RemoteStartTransaction, initiate the charging sequence: "
                    "send Authorize (if needed), then StartTransaction",
                exchanges=exchanges)

        return self.result(True,
            f"RemoteStartTransaction flow complete: txn={connection.active_transaction_id}",
            exchanges=exchanges)


class RemoteStopTransaction(OCPPTest):
    name = "remote_stop_transaction"
    category = "transactions"
    description = "RemoteStopTransaction → charger sends StopTransaction"
    ocpp_spec_ref = "OCPP 1.6 §5.5"
    severity = Severity.CRITICAL
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        txn_id = connection.active_transaction_id
        if txn_id is None:
            return self.skip("No active transaction — run RemoteStartTransaction first")

        exchanges = []

        # Send RemoteStopTransaction
        payload = {"transactionId": txn_id}
        resp = await connection.send_call_and_wait("RemoteStopTransaction", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "RemoteStopTransaction", "rstop", payload))

        if resp is None:
            return self.result(False,
                "RemoteStopTransaction timed out",
                expected="status: Accepted or Rejected",
                actual="Timeout",
                fix="Implement RemoteStopTransaction handler",
                exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "RemoteStopTransaction.conf", "rstop", resp))

        status = resp.get("status", "")
        if resp.get("_is_error"):
            return self.result(False,
                f"RemoteStopTransaction returned error: {resp.get('error_code')}",
                exchanges=exchanges)

        if status not in ("Accepted", "Rejected"):
            return self.result(False,
                f"Invalid status: '{status}'",
                expected="'Accepted' or 'Rejected'",
                actual=f"'{status}'",
                exchanges=exchanges)

        if status == "Rejected":
            return self.result(True,
                "RemoteStopTransaction rejected — charger doesn't have this transaction",
                exchanges=exchanges)

        # Wait for StopTransaction
        stop_item = await connection.wait_for_action("StopTransaction", timeout=30.0)
        if not stop_item:
            return self.result(False,
                "RemoteStopTransaction accepted but no StopTransaction received",
                expected="StopTransaction after RemoteStopTransaction(Accepted)",
                actual="No StopTransaction within 30s",
                fix="After accepting RemoteStopTransaction, end the charging session and "
                    "send StopTransaction with reason='Remote'",
                exchanges=exchanges)

        stop_payload = stop_item["payload"]
        exchanges.append(make_exchange("RECEIVED", "StopTransaction", stop_item["unique_id"], stop_payload))
        resp2 = stop_transaction_conf("Accepted")
        await connection.send_result(stop_item["unique_id"], resp2)
        exchanges.append(make_exchange("SENT", "StopTransaction.conf", stop_item["unique_id"], resp2))

        # Verify reason is 'Remote'
        stop_reason = stop_payload.get("reason", "")
        if stop_reason and stop_reason != "Remote":
            return self.result(True,
                f"StopTransaction received but reason='{stop_reason}' (expected 'Remote')",
                exchanges=exchanges,
                details={"warning": f"reason should be 'Remote' for remote stop, got '{stop_reason}'"})

        connection.active_transaction_id = None
        return self.result(True,
            f"RemoteStopTransaction flow complete — txn={txn_id} stopped",
            exchanges=exchanges)


ALL_TESTS = [
    StartTransactionRequiredFields,
    StartTransactionConnectorId,
    StopTransactionRequiredFields,
    StopTransactionMeterStopNotDecreasing,
    StopTransactionValidReason,
    TransactionIdConsistency,
    TransactionTimingAfterAuth,
    RemoteStartTransaction,
    RemoteStopTransaction,
]
