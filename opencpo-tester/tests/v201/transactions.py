"""
OCPP 2.0.1 Transaction tests.
TransactionEvent replaces Start/StopTransaction.
"""
import asyncio
import json
import time

from tests.base import OCPPTest, TestResult, Severity, make_exchange
from ocpp_messages.v201 import (
    transaction_event_conf, request_start_transaction_conf,
    request_stop_transaction_conf, authorize_conf,
    TRANSACTION_EVENT, TRIGGER_REASON, STOP_REASONS, CHARGING_STATE
)


class TransactionEventStructure(OCPPTest):
    name = "transaction_event_structure"
    category = "transactions"
    description = "TransactionEvent messages have correct structure and enum values"
    ocpp_spec_ref = "OCPP 2.0.1 §5.1"
    severity = Severity.CRITICAL
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        # Collect all TransactionEvent messages from log
        log_entries = connection.log.get_all()
        tx_events = []
        for e in log_entries:
            if e.get("parsed") and isinstance(e["parsed"], list):
                msg = e["parsed"]
                if msg[0] == 2 and msg[2] == "TransactionEvent":
                    tx_events.append({"uid": msg[1], "payload": msg[3]})

        if not tx_events:
            return self.skip("No TransactionEvent messages received yet")

        issues = []
        for tx in tx_events:
            payload = tx["payload"]
            event_type = payload.get("eventType")
            trigger_reason = payload.get("triggerReason")
            seq_no = payload.get("seqNo")
            transaction_info = payload.get("transactionInfo", {})
            timestamp = payload.get("timestamp")

            if not event_type:
                issues.append("Missing eventType")
            elif event_type not in TRANSACTION_EVENT:
                issues.append(f"Invalid eventType: '{event_type}' (must be {TRANSACTION_EVENT})")

            if not trigger_reason:
                issues.append("Missing triggerReason")
            elif trigger_reason not in TRIGGER_REASON:
                issues.append(f"Invalid triggerReason: '{trigger_reason}'")

            if seq_no is None:
                issues.append("Missing seqNo")
            elif not isinstance(seq_no, int) or seq_no < 0:
                issues.append(f"Invalid seqNo: {seq_no!r}")

            if not timestamp:
                issues.append("Missing timestamp")

            # Check transactionInfo
            if not transaction_info:
                issues.append("Missing transactionInfo")
            else:
                if not transaction_info.get("transactionId"):
                    issues.append("transactionInfo.transactionId missing")

        exchanges = [
            make_exchange("RECEIVED", "TransactionEvent", tx["uid"], tx["payload"])
            for tx in tx_events[:5]
        ]

        if issues:
            unique_issues = list(dict.fromkeys(issues))[:8]
            return self.result(False,
                f"TransactionEvent violations: {'; '.join(unique_issues)}",
                expected="eventType (Started/Updated/Ended), triggerReason, seqNo, transactionInfo, timestamp",
                actual="; ".join(unique_issues),
                fix="Ensure TransactionEvent includes all required fields with valid enum values. "
                    "eventType values: Started (begin), Updated (meter/status update), Ended (session end).",
                exchanges=exchanges)

        started = [t for t in tx_events if t["payload"].get("eventType") == "Started"]
        ended = [t for t in tx_events if t["payload"].get("eventType") == "Ended"]
        updated = [t for t in tx_events if t["payload"].get("eventType") == "Updated"]

        return self.result(True,
            f"TransactionEvent valid: {len(started)} Started, {len(updated)} Updated, {len(ended)} Ended",
            exchanges=exchanges)


class RequestStartTransaction201(OCPPTest):
    name = "request_start_transaction_201"
    category = "transactions"
    description = "RequestStartTransaction → charger sends TransactionEvent(Started)"
    ocpp_spec_ref = "OCPP 2.0.1 §5.1"
    severity = Severity.CRITICAL
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        valid_tag = self.config.get("valid_rfid_tag", "")
        exchanges = []

        import uuid
        payload = {
            "evseId": 1,
            "idToken": {"idToken": valid_tag, "type": "ISO14443"},
        }
        resp = await connection.send_call_and_wait("RequestStartTransaction", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "RequestStartTransaction", "rst201", payload))

        if resp is None:
            return self.result(False, "RequestStartTransaction timed out", exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "RequestStartTransaction.conf", "rst201", resp))

        if resp.get("_is_error"):
            return self.result(False, f"RequestStartTransaction error: {resp.get('error_code')}",
                               exchanges=exchanges)

        status = resp.get("status", "")
        if status not in ("Accepted", "Rejected"):
            return self.result(False,
                f"Invalid status: '{status}'",
                exchanges=exchanges)

        if status == "Rejected":
            return self.result(True, "RequestStartTransaction rejected (acceptable)", exchanges=exchanges)

        # Wait for TransactionEvent(Started)
        tx_item = await connection.wait_for_action("TransactionEvent", timeout=30.0)
        if not tx_item:
            return self.result(False,
                "RequestStartTransaction accepted but no TransactionEvent(Started) received",
                exchanges=exchanges,
                fix="After accepting RequestStartTransaction, send TransactionEvent with eventType='Started'")

        tx_payload = tx_item["payload"]
        exchanges.append(make_exchange("RECEIVED", "TransactionEvent", tx_item["unique_id"], tx_payload))
        await connection.send_result(tx_item["unique_id"], transaction_event_conf())

        event_type = tx_payload.get("eventType")
        if event_type != "Started":
            return self.result(False,
                f"First TransactionEvent has eventType='{event_type}', expected 'Started'",
                exchanges=exchanges)

        txn_id = tx_payload.get("transactionInfo", {}).get("transactionId")
        connection.active_transaction_id = txn_id

        return self.result(True,
            f"RequestStartTransaction flow complete: txn={txn_id}",
            exchanges=exchanges)


class RequestStopTransaction201(OCPPTest):
    name = "request_stop_transaction_201"
    category = "transactions"
    description = "RequestStopTransaction → charger sends TransactionEvent(Ended)"
    ocpp_spec_ref = "OCPP 2.0.1 §5.1"
    severity = Severity.CRITICAL
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        txn_id = connection.active_transaction_id
        if not txn_id:
            return self.skip("No active transaction")

        exchanges = []
        payload = {"transactionId": str(txn_id)}
        resp = await connection.send_call_and_wait("RequestStopTransaction", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "RequestStopTransaction", "rstop201", payload))

        if resp is None:
            return self.result(False, "RequestStopTransaction timed out", exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "RequestStopTransaction.conf", "rstop201", resp))

        status = resp.get("status", "")
        if status == "Rejected":
            return self.result(True, "RequestStopTransaction rejected", exchanges=exchanges)

        # Wait for TransactionEvent(Ended)
        tx_item = await connection.wait_for_action("TransactionEvent", timeout=30.0)
        if not tx_item:
            return self.result(False,
                "No TransactionEvent(Ended) after RequestStopTransaction",
                exchanges=exchanges)

        tx_payload = tx_item["payload"]
        exchanges.append(make_exchange("RECEIVED", "TransactionEvent", tx_item["unique_id"], tx_payload))
        await connection.send_result(tx_item["unique_id"], transaction_event_conf())

        event_type = tx_payload.get("eventType")
        if event_type != "Ended":
            return self.result(False,
                f"TransactionEvent eventType='{event_type}', expected 'Ended'",
                exchanges=exchanges)

        return self.result(True, "RequestStopTransaction → TransactionEvent(Ended) ✓", exchanges=exchanges)


ALL_TESTS = [
    TransactionEventStructure,
    RequestStartTransaction201,
    RequestStopTransaction201,
]
