"""
OCPP 2.0.1 MeterValues tests.
In 2.0.1, meter values are embedded in TransactionEvent(Updated) messages
and can also be sent as standalone MeterValues messages.
"""
import re
import time

from tests.base import OCPPTest, TestResult, Severity, make_exchange
from ocpp_messages.v201 import transaction_event_conf, meter_values_conf, TRIGGER_REASON

ISO8601_TZ_PATTERN = re.compile(
    r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'
    r'(\.\d+)?(Z|[+-]\d{2}:\d{2})$'
)

MEASURAND_COMMON = {
    "Current.Export", "Current.Import", "Current.Offered",
    "Energy.Active.Export.Register", "Energy.Active.Import.Register",
    "Energy.Active.Export.Interval", "Energy.Active.Import.Interval",
    "Energy.Reactive.Export.Register", "Energy.Reactive.Export.Interval",
    "Energy.Reactive.Import.Register", "Energy.Reactive.Import.Interval",
    "Frequency", "Power.Active.Export", "Power.Active.Import",
    "Power.Factor", "Power.Offered", "Power.Reactive.Export", "Power.Reactive.Import",
    "SoC", "Temperature", "Voltage",
}

READING_CONTEXT = {
    "Interruption.Begin", "Interruption.End", "Other", "Sample.Clock",
    "Sample.Periodic", "Transaction.Begin", "Transaction.End", "Trigger",
}

LOCATION = {"Body", "Cable", "EV", "Inlet", "Outlet"}
UNIT_OF_MEASURE_COMMON = {"Wh", "kWh", "varh", "kvarh", "W", "kW", "VA", "kVA",
                           "var", "kvar", "A", "V", "K", "Celsius", "Fahrenheit",
                           "Percent", "Hz"}


def _validate_sampled_value(sv: dict, idx: int) -> list[str]:
    """Validate a single sampledValue object. Returns list of issues."""
    issues = []
    if "value" not in sv:
        issues.append(f"sampledValue[{idx}] missing 'value'")
        return issues

    # value must be a number
    val = sv.get("value")
    if not isinstance(val, (int, float)):
        issues.append(f"sampledValue[{idx}].value must be numeric, got {type(val).__name__}")

    context = sv.get("context")
    if context and context not in READING_CONTEXT:
        issues.append(f"sampledValue[{idx}].context '{context}' not in valid set")

    measurand = sv.get("measurand")
    if measurand and measurand not in MEASURAND_COMMON:
        # Non-standard measurands are allowed as extensions
        pass

    location = sv.get("location")
    if location and location not in LOCATION:
        issues.append(f"sampledValue[{idx}].location '{location}' not in valid set")

    return issues


class TransactionEventMeterValues(OCPPTest):
    name = "tx_event_meter_values"
    category = "meter_values"
    description = "TransactionEvent(Updated) messages contain valid meterValue arrays"
    ocpp_spec_ref = "OCPP 2.0.1 §5.1 / §6.5"
    severity = Severity.WARNING
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        # Collect TransactionEvent messages with meterValue
        log_entries = connection.log.get_all()
        tx_events_with_meters = []
        for e in log_entries:
            if e.get("parsed") and isinstance(e["parsed"], list):
                msg = e["parsed"]
                if (msg[0] == 2 and msg[2] == "TransactionEvent"
                        and isinstance(msg[3], dict)
                        and msg[3].get("meterValue")):
                    tx_events_with_meters.append({"uid": msg[1], "payload": msg[3]})

        if not tx_events_with_meters:
            # Wait for TransactionEvent with meterValue
            deadline = time.monotonic() + 60.0
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                item = await connection.wait_for_action("TransactionEvent", timeout=min(remaining, 15.0))
                if not item:
                    break
                await connection.send_result(item["unique_id"], transaction_event_conf())
                if item["payload"].get("meterValue"):
                    tx_events_with_meters.append({"uid": item["unique_id"], "payload": item["payload"]})
                    break

        if not tx_events_with_meters:
            return self.result(False,
                "No TransactionEvent with meterValue received",
                expected="TransactionEvent(Updated) with meterValue array during active transaction",
                actual="No meterValue data in any TransactionEvent",
                fix="Send TransactionEvent with eventType='Updated' and meterValue periodically during charging")

        all_issues = []
        exchanges = []
        for tx in tx_events_with_meters[:5]:
            payload = tx["payload"]
            exchanges.append(make_exchange("RECEIVED", "TransactionEvent", tx["uid"], payload))
            meter_values = payload.get("meterValue", [])

            for mv_idx, mv in enumerate(meter_values):
                if not isinstance(mv, dict):
                    all_issues.append(f"meterValue[{mv_idx}] not an object")
                    continue

                # timestamp required
                ts = mv.get("timestamp")
                if not ts:
                    all_issues.append(f"meterValue[{mv_idx}] missing timestamp")
                elif not ISO8601_TZ_PATTERN.match(str(ts)):
                    all_issues.append(f"meterValue[{mv_idx}] invalid timestamp '{ts}'")

                # sampledValue array
                sampled = mv.get("sampledValue", [])
                if not sampled:
                    all_issues.append(f"meterValue[{mv_idx}] missing or empty sampledValue array")
                else:
                    for sv_idx, sv in enumerate(sampled):
                        all_issues.extend(_validate_sampled_value(sv, sv_idx))

        if all_issues:
            unique_issues = list(dict.fromkeys(all_issues))[:8]
            return self.result(False,
                f"MeterValue violations: {'; '.join(unique_issues)}",
                expected="meterValue: [{timestamp: ISO8601, sampledValue: [{value: number, ...}]}]",
                actual="; ".join(unique_issues),
                fix="Ensure each meterValue has a timestamp and at least one sampledValue "
                    "with a numeric 'value' field.",
                exchanges=exchanges)

        total_samples = sum(
            len(tx["payload"].get("meterValue", []))
            for tx in tx_events_with_meters
        )
        return self.result(True,
            f"MeterValues valid in {len(tx_events_with_meters)} TransactionEvent(s) "
            f"({total_samples} meter readings)",
            exchanges=exchanges)


class MeterValues201Standalone(OCPPTest):
    name = "meter_values_201_standalone"
    category = "meter_values"
    description = "Standalone MeterValues message (if sent) has valid structure"
    ocpp_spec_ref = "OCPP 2.0.1 §6.5"
    severity = Severity.INFO
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        log_entries = connection.log.get_all()
        mv_messages = []
        for e in log_entries:
            if e.get("parsed") and isinstance(e["parsed"], list):
                msg = e["parsed"]
                if msg[0] == 2 and msg[2] == "MeterValues":
                    mv_messages.append({"uid": msg[1], "payload": msg[3]})

        if not mv_messages:
            return self.result(True,
                "No standalone MeterValues messages sent (charger uses TransactionEvent for meter data — OK)",
                details={"note": "OCPP 2.0.1 prefers meter data in TransactionEvent"})

        issues = []
        exchanges = []
        for mv in mv_messages[:5]:
            payload = mv["payload"]
            exchanges.append(make_exchange("RECEIVED", "MeterValues", mv["uid"], payload))
            evse_id = payload.get("evseId")
            if evse_id is None:
                issues.append("MeterValues missing evseId")
            elif not isinstance(evse_id, int) or evse_id < 0:
                issues.append(f"evseId={evse_id!r} must be non-negative integer")

            meter_value = payload.get("meterValue", [])
            if not meter_value:
                issues.append("MeterValues missing meterValue array")

        if issues:
            unique = list(dict.fromkeys(issues))[:5]
            return self.result(False,
                "; ".join(unique),
                exchanges=exchanges,
                fix="MeterValues must include evseId and meterValue array")

        return self.result(True,
            f"Standalone MeterValues structure valid ({len(mv_messages)} message(s))",
            exchanges=exchanges)


class EnergyImportRegisterMeasurand(OCPPTest):
    name = "energy_import_register_measurand"
    category = "meter_values"
    description = "TransactionEvent includes Energy.Active.Import.Register measurand for billing"
    ocpp_spec_ref = "OCPP 2.0.1 §6.5"
    severity = Severity.WARNING
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        log_entries = connection.log.get_all()
        all_measurands: set = set()
        exchanges = []

        for e in log_entries:
            if e.get("parsed") and isinstance(e["parsed"], list):
                msg = e["parsed"]
                if msg[0] == 2 and msg[2] == "TransactionEvent":
                    payload = msg[3]
                    if payload.get("meterValue"):
                        exchanges.append(make_exchange("RECEIVED", "TransactionEvent", msg[1], payload))
                        for mv in payload["meterValue"]:
                            for sv in mv.get("sampledValue", []):
                                m = sv.get("measurand")
                                if m:
                                    all_measurands.add(m)

        if not all_measurands:
            return self.skip("No meter data captured yet — run a transaction first")

        if "Energy.Active.Import.Register" in all_measurands:
            return self.result(True,
                f"Energy.Active.Import.Register present in meter data",
                exchanges=exchanges,
                details={"measurands_seen": sorted(all_measurands)})

        return self.result(False,
            "Energy.Active.Import.Register measurand not found in meter data",
            expected="At least one sampledValue with measurand='Energy.Active.Import.Register'",
            actual=f"Measurands seen: {sorted(all_measurands)}",
            fix="Include Energy.Active.Import.Register in TransactionEvent meterValue for billing accuracy",
            exchanges=exchanges,
            details={"measurands_seen": sorted(all_measurands)})


ALL_TESTS = [
    TransactionEventMeterValues,
    MeterValues201Standalone,
    EnergyImportRegisterMeasurand,
]
