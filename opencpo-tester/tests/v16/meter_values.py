"""
OCPP 1.6 MeterValues tests.
Deep validation of meter value fields, units, monotonicity, and timing.
"""
import asyncio
import json
import re
import time
from collections import defaultdict

from tests.base import OCPPTest, TestResult, Severity, make_exchange
from ocpp_messages.v16 import (
    meter_values_conf, MEASURANDS, MEASURAND_UNITS, PHASES, LOCATIONS,
    FORMATS, CONTEXTS
)

ISO8601_TZ_PATTERN = re.compile(
    r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$'
)

# Units that require numeric conversion
ENERGY_MEASURANDS = {
    "Energy.Active.Import.Register",
    "Energy.Active.Export.Register",
    "Energy.Active.Import.Interval",
    "Energy.Active.Export.Interval",
}

POWER_MEASURANDS = {
    "Power.Active.Import",
    "Power.Active.Export",
}

CURRENT_MEASURANDS = {
    "Current.Import",
    "Current.Export",
    "Current.Offered",
}


def collect_meter_values_from_log(log) -> list[dict]:
    """Extract all MeterValues messages from the connection log."""
    results = []
    for e in log.get_all():
        if e.get("parsed") and isinstance(e["parsed"], list):
            msg = e["parsed"]
            if len(msg) >= 4 and msg[0] == 2 and msg[2] == "MeterValues":
                results.append({"uid": msg[1], "payload": msg[3]})
    return results


class MeterValuesStructure(OCPPTest):
    name = "meter_values_structure"
    category = "meter_values"
    description = "MeterValues messages have correct structure: connectorId, meterValue array, sampledValue array"
    ocpp_spec_ref = "OCPP 1.6 §5.10"
    severity = Severity.CRITICAL
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        mv_messages = collect_meter_values_from_log(connection.log)
        if not mv_messages:
            return self.result(False,
                "No MeterValues messages received",
                expected="MeterValues sent during charging session",
                actual="No MeterValues received",
                fix="Configure charger to send MeterValues during charging. "
                    "Set MeterValueSampleInterval and MeterValuesSampledData.")

        issues = []
        for mv in mv_messages:
            payload = mv["payload"]
            if "connectorId" not in payload:
                issues.append(f"Missing connectorId in MeterValues")
            if "meterValue" not in payload:
                issues.append(f"Missing meterValue array")
            else:
                for i, mv_item in enumerate(payload.get("meterValue", [])):
                    if "sampledValue" not in mv_item:
                        issues.append(f"meterValue[{i}] missing sampledValue array")
                    if "timestamp" not in mv_item:
                        issues.append(f"meterValue[{i}] missing timestamp")

        exchanges = [
            make_exchange("RECEIVED", "MeterValues", mv["uid"], mv["payload"])
            for mv in mv_messages[:5]  # Limit for report readability
        ]

        if issues:
            return self.result(False,
                f"MeterValues structure issues: {'; '.join(issues[:5])}",
                expected="meterValue: [{timestamp, sampledValue: [{value, measurand, unit, ...}]}]",
                actual="; ".join(issues[:5]),
                fix="Ensure MeterValues payload has connectorId, meterValue array with "
                    "timestamp and sampledValue array per reading",
                exchanges=exchanges)

        return self.result(True,
            f"MeterValues structure valid ({len(mv_messages)} messages, "
            f"{sum(len(m['payload'].get('meterValue', [])) for m in mv_messages)} readings)",
            exchanges=exchanges)


class MeterValuesRequiredMeasurand(OCPPTest):
    name = "meter_values_energy_register"
    category = "meter_values"
    description = "MeterValues include Energy.Active.Import.Register measurand"
    ocpp_spec_ref = "OCPP 1.6 §5.10"
    severity = Severity.CRITICAL
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        mv_messages = collect_meter_values_from_log(connection.log)
        if not mv_messages:
            return self.skip("No MeterValues captured")

        has_energy = False
        for mv in mv_messages:
            for mv_item in mv["payload"].get("meterValue", []):
                for sv in mv_item.get("sampledValue", []):
                    measurand = sv.get("measurand", "Energy.Active.Import.Register")
                    if measurand in ENERGY_MEASURANDS:
                        has_energy = True
                        break

        exchanges = [
            make_exchange("RECEIVED", "MeterValues", mv["uid"], mv["payload"])
            for mv in mv_messages[:3]
        ]

        if not has_energy:
            return self.result(False,
                "No Energy.Active.Import.Register measurand found in any MeterValues message",
                expected="Energy.Active.Import.Register in sampledValue (required for billing)",
                actual="No energy measurand found",
                fix="Configure MeterValuesSampledData to include Energy.Active.Import.Register. "
                    "This measurand is required for accurate billing.",
                exchanges=exchanges)

        return self.result(True,
            "Energy.Active.Import.Register measurand present",
            exchanges=exchanges)


class MeterValuesSampledValueFields(OCPPTest):
    name = "meter_values_sampled_value_fields"
    category = "meter_values"
    description = "sampledValue fields use valid enum values (measurand, unit, phase, location, context)"
    ocpp_spec_ref = "OCPP 1.6 §5.10"
    severity = Severity.WARNING
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        mv_messages = collect_meter_values_from_log(connection.log)
        if not mv_messages:
            return self.skip("No MeterValues captured")

        issues = []
        for mv in mv_messages[:10]:
            for mv_item in mv["payload"].get("meterValue", []):
                for sv in mv_item.get("sampledValue", []):
                    measurand = sv.get("measurand", "Energy.Active.Import.Register")
                    phase = sv.get("phase")
                    location = sv.get("location")
                    fmt = sv.get("format")
                    context = sv.get("context")
                    unit = sv.get("unit")

                    if measurand and measurand not in MEASURANDS:
                        issues.append(f"Unknown measurand: '{measurand}'")

                    if phase and phase not in PHASES:
                        issues.append(f"Invalid phase: '{phase}'")

                    if location and location not in LOCATIONS:
                        issues.append(f"Invalid location: '{location}'")

                    if fmt and fmt not in FORMATS:
                        issues.append(f"Invalid format: '{fmt}'")

                    if context and context not in CONTEXTS:
                        issues.append(f"Invalid context: '{context}'")

                    # Validate unit for known measurands
                    if measurand and unit and measurand in MEASURAND_UNITS:
                        allowed_units = MEASURAND_UNITS[measurand]
                        if unit not in allowed_units:
                            issues.append(
                                f"Wrong unit for {measurand}: got '{unit}', "
                                f"expected one of {allowed_units}"
                            )

        exchanges = [
            make_exchange("RECEIVED", "MeterValues", mv["uid"], mv["payload"])
            for mv in mv_messages[:3]
        ]

        if issues:
            unique_issues = list(dict.fromkeys(issues))[:10]
            return self.result(False,
                f"sampledValue field violations: {'; '.join(unique_issues)}",
                expected="Valid OCPP 1.6 enum values for measurand, unit, phase, location, context",
                actual="; ".join(unique_issues),
                fix="Use only OCPP 1.6 compliant enum values in sampledValue. "
                    "Common fixes: use 'Wh' or 'kWh' for energy, 'W'/'kW' for power, "
                    "'A' for current, 'V' for voltage.",
                exchanges=exchanges)

        return self.result(True,
            "All sampledValue enum fields valid",
            exchanges=exchanges)


class MeterValuesNumericValues(OCPPTest):
    name = "meter_values_numeric_values"
    category = "meter_values"
    description = "All sampledValue.value fields are parseable as numbers"
    ocpp_spec_ref = "OCPP 1.6 §5.10"
    severity = Severity.CRITICAL
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        mv_messages = collect_meter_values_from_log(connection.log)
        if not mv_messages:
            return self.skip("No MeterValues captured")

        non_numeric = []
        for mv in mv_messages:
            for mv_item in mv["payload"].get("meterValue", []):
                for sv in mv_item.get("sampledValue", []):
                    val = sv.get("value", "")
                    if val == "" or val is None:
                        continue
                    try:
                        float(str(val))
                    except (ValueError, TypeError):
                        measurand = sv.get("measurand", "?")
                        non_numeric.append(f"measurand={measurand} value={val!r}")

        exchanges = [
            make_exchange("RECEIVED", "MeterValues", mv["uid"], mv["payload"])
            for mv in mv_messages[:3]
        ]

        if non_numeric:
            return self.result(False,
                f"Non-numeric values: {'; '.join(non_numeric[:5])}",
                expected="All sampledValue.value fields are numeric strings",
                actual="; ".join(non_numeric[:5]),
                fix="Ensure all sampledValue.value fields contain numeric strings "
                    "(e.g. '12345', '230.5', '16.0'). Do not include units in the value field.",
                exchanges=exchanges)

        return self.result(True, "All sampledValue values are numeric", exchanges=exchanges)


class MeterValuesTimestampMonotonic(OCPPTest):
    name = "meter_values_timestamp_monotonic"
    category = "meter_values"
    description = "MeterValues timestamps advance monotonically during a session"
    ocpp_spec_ref = "OCPP 1.6 §5.10"
    severity = Severity.WARNING
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        mv_messages = collect_meter_values_from_log(connection.log)
        if len(mv_messages) < 2:
            return self.skip("Need at least 2 MeterValues messages to check monotonicity")

        from datetime import datetime, timezone

        prev_ts = None
        violations = []
        timestamps_seen = []

        for mv in mv_messages:
            for mv_item in mv["payload"].get("meterValue", []):
                ts_str = mv_item.get("timestamp", "")
                if not ts_str:
                    continue
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    timestamps_seen.append(ts)
                    if prev_ts and ts < prev_ts:
                        violations.append(
                            f"Timestamp went backwards: {prev_ts.isoformat()} → {ts.isoformat()}"
                        )
                    prev_ts = ts
                except ValueError:
                    violations.append(f"Cannot parse timestamp: '{ts_str}'")

        if violations:
            return self.result(False,
                f"Non-monotonic timestamps: {'; '.join(violations[:3])}",
                expected="Timestamps strictly increasing across MeterValues",
                actual="; ".join(violations[:3]),
                fix="Ensure charger clock is synchronized (NTP) and timestamps always advance. "
                    "Do not send duplicate or backwards timestamps.")

        if len(timestamps_seen) >= 2:
            span = (timestamps_seen[-1] - timestamps_seen[0]).total_seconds()
            return self.result(True,
                f"Timestamps monotonically increasing ({len(timestamps_seen)} readings over {span:.0f}s)",
                details={"first_ts": timestamps_seen[0].isoformat(),
                         "last_ts": timestamps_seen[-1].isoformat()})

        return self.result(True, "Timestamps valid")


class MeterValuesEnergyNotDecreasing(OCPPTest):
    name = "meter_values_energy_non_decreasing"
    category = "meter_values"
    description = "Energy.Active.Import.Register values are non-decreasing during session"
    ocpp_spec_ref = "OCPP 1.6 §5.10"
    severity = Severity.CRITICAL
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        mv_messages = collect_meter_values_from_log(connection.log)
        if not mv_messages:
            return self.skip("No MeterValues captured")

        energy_readings = []
        for mv in mv_messages:
            for mv_item in mv["payload"].get("meterValue", []):
                for sv in mv_item.get("sampledValue", []):
                    measurand = sv.get("measurand", "Energy.Active.Import.Register")
                    if measurand in ENERGY_MEASURANDS:
                        try:
                            val = float(sv["value"])
                            unit = sv.get("unit", "Wh")
                            # Normalize to Wh
                            if unit == "kWh":
                                val *= 1000
                            energy_readings.append(val)
                        except (ValueError, KeyError):
                            pass

        if len(energy_readings) < 2:
            return self.skip("Need at least 2 energy readings to check monotonicity")

        violations = []
        for i in range(1, len(energy_readings)):
            if energy_readings[i] < energy_readings[i-1]:
                diff = energy_readings[i-1] - energy_readings[i]
                violations.append(
                    f"Energy decreased at reading {i}: {energy_readings[i-1]:.1f} → {energy_readings[i]:.1f} Wh "
                    f"(dropped {diff:.1f} Wh)"
                )

        if violations:
            return self.result(False,
                f"Energy values not monotonic: {'; '.join(violations[:3])}",
                expected="Energy.Active.Import.Register is cumulative lifetime counter — must never decrease",
                actual="; ".join(violations[:3]),
                fix="The energy register must be a cumulative (non-resetting) counter. "
                    "Do NOT reset to 0 between sessions or during charging. "
                    "If using session-relative values, change to absolute register values.",
                details={"readings_wh": energy_readings[:20]})

        min_e = min(energy_readings)
        max_e = max(energy_readings)
        return self.result(True,
            f"Energy readings non-decreasing: {min_e:.1f} → {max_e:.1f} Wh "
            f"({len(energy_readings)} readings)",
            details={"min_wh": min_e, "max_wh": max_e, "count": len(energy_readings)})


class MeterValuesInterval(OCPPTest):
    name = "meter_values_interval"
    category = "meter_values"
    description = "MeterValues sent at configured MeterValueSampleInterval (±10% tolerance)"
    ocpp_spec_ref = "OCPP 1.6 §5.10"
    severity = Severity.WARNING
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        from datetime import datetime

        expected_interval = self.config.get("meter_interval",
                            int(connection.known_config.get("MeterValueSampleInterval", 10)))

        # Collect meter value timestamps in order
        timestamps = []
        for e in connection.log.get_all():
            if e.get("parsed") and isinstance(e["parsed"], list):
                msg = e["parsed"]
                if msg[0] == 2 and msg[2] == "MeterValues":
                    timestamps.append(e["ts_mono"])

        if len(timestamps) < 2:
            return self.skip(f"Need at least 2 MeterValues to measure interval "
                             f"(got {len(timestamps)})")

        intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
        avg_interval = sum(intervals) / len(intervals)
        min_interval = min(intervals)
        max_interval = max(intervals)

        tolerance = 0.10
        low = expected_interval * (1 - tolerance)
        high = expected_interval * (1 + tolerance)

        out_of_range = [iv for iv in intervals if not (low <= iv <= high)]

        details = {
            "expected_interval": expected_interval,
            "avg_interval": round(avg_interval, 2),
            "min_interval": round(min_interval, 2),
            "max_interval": round(max_interval, 2),
            "samples": len(intervals),
        }

        if out_of_range:
            pct_oob = len(out_of_range) / len(intervals) * 100
            return self.result(False,
                f"MeterValues interval out of tolerance: avg={avg_interval:.1f}s "
                f"(expected {expected_interval}s ±10%, {pct_oob:.0f}% samples out of range)",
                expected=f"MeterValues every {expected_interval}s ±10% ({low:.1f}–{high:.1f}s)",
                actual=f"avg={avg_interval:.1f}s, min={min_interval:.1f}s, max={max_interval:.1f}s",
                fix=f"Set MeterValueSampleInterval={expected_interval} and ensure the charger "
                    f"sends meter values consistently without drift or jitter",
                details=details)

        return self.result(True,
            f"MeterValues interval: avg={avg_interval:.1f}s (expected {expected_interval}s ±10%)",
            details=details)


class MeterValuesTransactionId(OCPPTest):
    name = "meter_values_transaction_id"
    category = "meter_values"
    description = "MeterValues during transaction include the correct transactionId"
    ocpp_spec_ref = "OCPP 1.6 §5.10"
    severity = Severity.WARNING
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        txn_id = connection.active_transaction_id
        mv_messages = collect_meter_values_from_log(connection.log)

        if not mv_messages:
            return self.skip("No MeterValues captured")

        if txn_id is None:
            return self.skip("No active transaction ID to validate against")

        missing_txn = []
        wrong_txn = []
        for mv in mv_messages:
            payload = mv["payload"]
            mv_txn = payload.get("transactionId")
            if mv_txn is None:
                missing_txn.append(mv["uid"])
            elif mv_txn != txn_id:
                wrong_txn.append(f"uid={mv['uid']} expected={txn_id} got={mv_txn}")

        issues = []
        if missing_txn:
            issues.append(f"{len(missing_txn)} MeterValues missing transactionId")
        if wrong_txn:
            issues.append(f"Wrong transactionId: {'; '.join(wrong_txn[:3])}")

        if issues:
            return self.result(False,
                "; ".join(issues),
                expected=f"transactionId={txn_id} in all MeterValues during transaction",
                actual="; ".join(issues),
                fix="Include transactionId in MeterValues messages sent during an active transaction. "
                    "Use the transactionId received from StartTransaction.conf.",
                details={"expected_txn_id": txn_id})

        return self.result(True,
            f"All {len(mv_messages)} MeterValues include correct transactionId={txn_id}")


ALL_TESTS = [
    MeterValuesStructure,
    MeterValuesRequiredMeasurand,
    MeterValuesSampledValueFields,
    MeterValuesNumericValues,
    MeterValuesTimestampMonotonic,
    MeterValuesEnergyNotDecreasing,
    MeterValuesInterval,
    MeterValuesTransactionId,
]
