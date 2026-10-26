"""
OCPP 1.6 StatusNotification tests.
Validates status values, error codes, connector IDs, and timestamp format.
"""
import asyncio
import json
import re
import time

from tests.base import OCPPTest, TestResult, TestStatus, Severity, make_exchange
from ocpp_messages.v16 import (
    CONNECTOR_STATUS, ERROR_CODES, status_notification_conf, FIELD_LENGTHS
)

# ISO 8601 with timezone pattern
ISO8601_TZ_PATTERN = re.compile(
    r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'
    r'(\.\d+)?(Z|[+-]\d{2}:\d{2})$'
)


def validate_iso8601_tz(ts_str: str) -> bool:
    """Check if a timestamp string is ISO 8601 with timezone."""
    if not ts_str:
        return False
    return bool(ISO8601_TZ_PATTERN.match(str(ts_str)))


class StatusNotificationOnBoot(OCPPTest):
    name = "status_notification_on_boot"
    category = "status"
    description = "Charger sends StatusNotification for connector 0 and all physical connectors on boot"
    ocpp_spec_ref = "OCPP 1.6 §4.7"
    severity = Severity.CRITICAL
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        statuses = connection.status_by_connector
        if not statuses:
            return self.result(False,
                "No StatusNotification messages received",
                expected="StatusNotification for connector 0 and each physical connector on boot",
                actual="No StatusNotification received",
                fix="Send StatusNotification for connector 0 (charger-level) and each connector "
                    "after BootNotification is accepted")

        has_connector_0 = 0 in statuses
        num_physical = self.config.get("num_connectors", 1)
        missing_connectors = [c for c in range(1, num_physical + 1) if c not in statuses]

        exchanges = [
            make_exchange("RECEIVED", "StatusNotification", str(cid), payload)
            for cid, payload in statuses.items()
        ]

        issues = []
        if not has_connector_0:
            issues.append("Missing StatusNotification for connector 0 (charger-level status)")
        if missing_connectors:
            issues.append(f"Missing StatusNotification for connectors: {missing_connectors}")

        if issues:
            return self.result(False,
                "; ".join(issues),
                expected=f"StatusNotification for connectors 0..{num_physical}",
                actual=f"Received for connectors: {sorted(statuses.keys())}",
                fix="Send StatusNotification for connector 0 AND each physical connector "
                    "(1, 2, ...) after boot",
                exchanges=exchanges,
                details={"received_connectors": sorted(statuses.keys())})

        return self.result(True,
            f"StatusNotification received for connectors: {sorted(statuses.keys())}",
            exchanges=exchanges)


class StatusNotificationValidStatus(OCPPTest):
    name = "status_notification_valid_status"
    category = "status"
    description = "All StatusNotification messages use valid status enum values"
    ocpp_spec_ref = "OCPP 1.6 §4.7"
    severity = Severity.CRITICAL
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        statuses = connection.status_by_connector
        if not statuses:
            return self.skip("No StatusNotification captured")

        violations = []
        for connector_id, payload in statuses.items():
            status = payload.get("status", "")
            if status not in CONNECTOR_STATUS:
                violations.append(f"Connector {connector_id}: invalid status '{status}'")

        exchanges = [
            make_exchange("RECEIVED", "StatusNotification", str(cid), p)
            for cid, p in statuses.items()
        ]

        if violations:
            return self.result(False,
                "; ".join(violations),
                expected=f"Status must be one of: {sorted(CONNECTOR_STATUS)}",
                actual="; ".join(violations),
                fix=f"Use only valid OCPP 1.6 status values: {sorted(CONNECTOR_STATUS)}",
                exchanges=exchanges)

        statuses_seen = {p.get("status") for p in statuses.values()}
        return self.result(True,
            f"All status values valid (seen: {sorted(statuses_seen)})",
            exchanges=exchanges)


class StatusNotificationValidErrorCode(OCPPTest):
    name = "status_notification_valid_error_code"
    category = "status"
    description = "All StatusNotification messages use valid errorCode enum values"
    ocpp_spec_ref = "OCPP 1.6 §4.7"
    severity = Severity.CRITICAL
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        statuses = connection.status_by_connector
        if not statuses:
            return self.skip("No StatusNotification captured")

        violations = []
        for connector_id, payload in statuses.items():
            error_code = payload.get("errorCode", "NoError")
            if error_code not in ERROR_CODES:
                violations.append(f"Connector {connector_id}: invalid errorCode '{error_code}'")

        exchanges = [
            make_exchange("RECEIVED", "StatusNotification", str(cid), p)
            for cid, p in statuses.items()
        ]

        if violations:
            return self.result(False,
                "; ".join(violations),
                expected=f"errorCode must be one of: {sorted(ERROR_CODES)}",
                actual="; ".join(violations),
                fix=f"Use only valid OCPP 1.6 errorCode values. 'NoError' is the standard "
                    f"value when there is no fault.",
                exchanges=exchanges)

        error_codes_seen = {p.get("errorCode", "NoError") for p in statuses.values()}
        return self.result(True,
            f"All errorCode values valid (seen: {sorted(error_codes_seen)})",
            exchanges=exchanges)


class StatusNotificationTimestamp(OCPPTest):
    name = "status_notification_timestamp"
    category = "status"
    description = "StatusNotification timestamp is ISO 8601 with timezone"
    ocpp_spec_ref = "OCPP 1.6 §4.7"
    severity = Severity.WARNING
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        statuses = connection.status_by_connector
        if not statuses:
            return self.skip("No StatusNotification captured")

        violations = []
        for connector_id, payload in statuses.items():
            ts = payload.get("timestamp", "")
            if ts and not validate_iso8601_tz(ts):
                violations.append(f"Connector {connector_id}: invalid timestamp '{ts}'")
            elif not ts:
                # timestamp is optional but strongly recommended
                violations.append(f"Connector {connector_id}: timestamp missing (optional but recommended)")

        exchanges = [
            make_exchange("RECEIVED", "StatusNotification", str(cid), p)
            for cid, p in statuses.items()
        ]

        if violations:
            # Only fail on format violations, not missing timestamps
            format_violations = [v for v in violations if "invalid timestamp" in v]
            if format_violations:
                return self.result(False,
                    "; ".join(format_violations),
                    expected="ISO 8601 timestamp with timezone, e.g. '2024-01-15T10:30:00+00:00' or '2024-01-15T10:30:00Z'",
                    actual="; ".join(format_violations),
                    fix="Format timestamps as ISO 8601 with UTC offset. Example: "
                        "datetime.now(timezone.utc).isoformat()",
                    exchanges=exchanges)
            else:
                return self.result(True,
                    "Timestamps missing but format not violating spec",
                    exchanges=exchanges,
                    details={"warnings": violations})

        return self.result(True,
            "All timestamps are valid ISO 8601 with timezone",
            exchanges=exchanges)


class StatusNotificationVendorFields(OCPPTest):
    name = "status_notification_vendor_fields"
    category = "status"
    description = "Optional vendorId and vendorErrorCode fields are within length limits"
    ocpp_spec_ref = "OCPP 1.6 §4.7"
    severity = Severity.WARNING
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        statuses = connection.status_by_connector
        if not statuses:
            return self.skip("No StatusNotification captured")

        violations = []
        for connector_id, payload in statuses.items():
            vendor_id = payload.get("vendorId", "")
            vendor_err = payload.get("vendorErrorCode", "")
            if vendor_id and len(vendor_id) > FIELD_LENGTHS.get("vendorId", 255):
                violations.append(f"Connector {connector_id}: vendorId too long ({len(vendor_id)} chars)")
            if vendor_err and len(vendor_err) > FIELD_LENGTHS.get("vendorErrorCode", 50):
                violations.append(f"Connector {connector_id}: vendorErrorCode too long ({len(vendor_err)} chars)")

        exchanges = [
            make_exchange("RECEIVED", "StatusNotification", str(cid), p)
            for cid, p in statuses.items()
        ]

        if violations:
            return self.result(False, "; ".join(violations),
                exchanges=exchanges,
                fix="Truncate vendorId and vendorErrorCode to OCPP spec limits")

        return self.result(True, "Vendor fields OK (or not present)", exchanges=exchanges)


class StatusNotificationConnectorZero(OCPPTest):
    name = "status_notification_connector_zero"
    category = "status"
    description = "Connector 0 represents the charger as a whole, not a physical connector"
    ocpp_spec_ref = "OCPP 1.6 §4.7"
    severity = Severity.INFO
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        statuses = connection.status_by_connector

        connector_0 = statuses.get(0)
        if not connector_0:
            return self.result(True,
                "Connector 0 StatusNotification not required but recommended",
                details={"note": "Some chargers omit connector 0 — this is acceptable"})

        status = connector_0.get("status", "")
        error_code = connector_0.get("errorCode", "NoError")

        exchanges = [make_exchange("RECEIVED", "StatusNotification", "0", connector_0)]

        return self.result(True,
            f"Connector 0: status='{status}' errorCode='{error_code}'",
            exchanges=exchanges)


ALL_TESTS = [
    StatusNotificationOnBoot,
    StatusNotificationValidStatus,
    StatusNotificationValidErrorCode,
    StatusNotificationTimestamp,
    StatusNotificationVendorFields,
    StatusNotificationConnectorZero,
]
