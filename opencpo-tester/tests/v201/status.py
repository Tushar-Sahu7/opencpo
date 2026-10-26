"""
OCPP 2.0.1 StatusNotification tests.
In 2.0.1, status is reported per EVSE/Connector pair.
ConnectorStatus replaces the 1.6 ChargePointStatus enum.
"""
import re

from tests.base import OCPPTest, TestResult, Severity, make_exchange
from ocpp_messages.v201 import CONNECTOR_STATUS, status_notification_conf

ISO8601_TZ_PATTERN = re.compile(
    r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'
    r'(\.\d+)?(Z|[+-]\d{2}:\d{2})$'
)


class StatusNotification201OnBoot(OCPPTest):
    name = "status201_on_boot"
    category = "status"
    description = "Charger sends StatusNotification for each EVSE/Connector on boot"
    ocpp_spec_ref = "OCPP 2.0.1 §4.7"
    severity = Severity.CRITICAL
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        statuses = connection.status_by_connector
        if not statuses:
            return self.result(False,
                "No StatusNotification messages received",
                expected="StatusNotification for each EVSE/Connector after BootNotification",
                actual="No StatusNotification received",
                fix="Send StatusNotification for each physical EVSE and connector after BootNotification is accepted")

        exchanges = [
            make_exchange("RECEIVED", "StatusNotification", str(eid), payload)
            for eid, payload in statuses.items()
        ]

        num_connectors = self.config.get("charger", {}).get("num_connectors",
                         self.config.get("num_connectors", 1))

        missing = [i for i in range(1, num_connectors + 1) if i not in statuses]
        if missing:
            return self.result(False,
                f"Missing StatusNotification for EVSEs: {missing}",
                expected=f"StatusNotification for EVSEs 1..{num_connectors}",
                actual=f"Received for EVSEs: {sorted(statuses.keys())}",
                fix="Send StatusNotification for every physical EVSE after boot",
                exchanges=exchanges)

        return self.result(True,
            f"StatusNotification received for {len(statuses)} EVSE(s): {sorted(statuses.keys())}",
            exchanges=exchanges)


class StatusNotification201ValidStatus(OCPPTest):
    name = "status201_valid_status"
    category = "status"
    description = "StatusNotification messages use valid 2.0.1 ConnectorStatus enum values"
    ocpp_spec_ref = "OCPP 2.0.1 §4.7"
    severity = Severity.CRITICAL
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        statuses = connection.status_by_connector
        if not statuses:
            return self.skip("No StatusNotification captured")

        violations = []
        for evse_id, payload in statuses.items():
            status = payload.get("connectorStatus", "")
            if status not in CONNECTOR_STATUS:
                violations.append(f"EVSE {evse_id}: invalid connectorStatus '{status}'")

        exchanges = [
            make_exchange("RECEIVED", "StatusNotification", str(eid), p)
            for eid, p in statuses.items()
        ]

        if violations:
            return self.result(False,
                "; ".join(violations),
                expected=f"connectorStatus must be one of: {sorted(CONNECTOR_STATUS)}",
                actual="; ".join(violations),
                fix=f"Use only valid OCPP 2.0.1 ConnectorStatus values: {sorted(CONNECTOR_STATUS)}",
                exchanges=exchanges)

        seen = {p.get("connectorStatus") for p in statuses.values()}
        return self.result(True,
            f"All connectorStatus values valid (seen: {sorted(seen)})",
            exchanges=exchanges)


class StatusNotification201RequiredFields(OCPPTest):
    name = "status201_required_fields"
    category = "status"
    description = "StatusNotification 2.0.1 has required fields: timestamp, connectorStatus, evseId, connectorId"
    ocpp_spec_ref = "OCPP 2.0.1 §4.7"
    severity = Severity.CRITICAL
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        statuses = connection.status_by_connector
        if not statuses:
            return self.skip("No StatusNotification captured")

        violations = []
        for evse_id, payload in statuses.items():
            missing = []
            if "timestamp" not in payload:
                missing.append("timestamp")
            if "connectorStatus" not in payload:
                missing.append("connectorStatus")
            if "evseId" not in payload:
                missing.append("evseId")
            if "connectorId" not in payload:
                missing.append("connectorId")
            if missing:
                violations.append(f"EVSE {evse_id}: missing {missing}")

        exchanges = [
            make_exchange("RECEIVED", "StatusNotification", str(eid), p)
            for eid, p in statuses.items()
        ]

        if violations:
            return self.result(False,
                "; ".join(violations),
                expected="All StatusNotification messages include: timestamp, connectorStatus, evseId, connectorId",
                actual="; ".join(violations),
                fix="Add all required fields to StatusNotification per OCPP 2.0.1 §4.7",
                exchanges=exchanges)

        return self.result(True,
            f"All StatusNotification messages have required fields ({len(statuses)} EVSE(s))",
            exchanges=exchanges)


class StatusNotification201Timestamp(OCPPTest):
    name = "status201_timestamp_format"
    category = "status"
    description = "StatusNotification timestamp is ISO 8601 with timezone"
    ocpp_spec_ref = "OCPP 2.0.1 §4.7"
    severity = Severity.WARNING
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        statuses = connection.status_by_connector
        if not statuses:
            return self.skip("No StatusNotification captured")

        violations = []
        for evse_id, payload in statuses.items():
            ts = payload.get("timestamp", "")
            if ts and not ISO8601_TZ_PATTERN.match(str(ts)):
                violations.append(f"EVSE {evse_id}: invalid timestamp '{ts}'")

        exchanges = [
            make_exchange("RECEIVED", "StatusNotification", str(eid), p)
            for eid, p in statuses.items()
        ]

        if violations:
            return self.result(False,
                "; ".join(violations),
                expected="ISO 8601 with timezone, e.g. '2024-01-15T10:30:00Z'",
                actual="; ".join(violations),
                fix="Format timestamp as ISO 8601 with UTC offset: datetime.now(timezone.utc).isoformat()",
                exchanges=exchanges)

        return self.result(True,
            "All timestamps are valid ISO 8601 with timezone",
            exchanges=exchanges)


class StatusNotification201EvseConnectorIds(OCPPTest):
    name = "status201_evse_connector_ids"
    category = "status"
    description = "evseId and connectorId in StatusNotification are positive integers"
    ocpp_spec_ref = "OCPP 2.0.1 §4.7"
    severity = Severity.WARNING
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        statuses = connection.status_by_connector
        if not statuses:
            return self.skip("No StatusNotification captured")

        violations = []
        for evse_id, payload in statuses.items():
            eid = payload.get("evseId")
            cid = payload.get("connectorId")
            if eid is not None and (not isinstance(eid, int) or eid < 1):
                violations.append(f"evseId={eid!r} must be positive integer ≥1")
            if cid is not None and (not isinstance(cid, int) or cid < 1):
                violations.append(f"connectorId={cid!r} must be positive integer ≥1")

        exchanges = [
            make_exchange("RECEIVED", "StatusNotification", str(eid), p)
            for eid, p in statuses.items()
        ]

        if violations:
            return self.result(False,
                "; ".join(violations),
                expected="evseId ≥1, connectorId ≥1 (positive integers, no zero)",
                actual="; ".join(violations),
                fix="In OCPP 2.0.1, EVSEs are numbered from 1. Use evseId=1, connectorId=1 for single-connector chargers.",
                exchanges=exchanges)

        return self.result(True,
            f"All evseId and connectorId values are valid positive integers",
            exchanges=exchanges)


ALL_TESTS = [
    StatusNotification201OnBoot,
    StatusNotification201RequiredFields,
    StatusNotification201ValidStatus,
    StatusNotification201Timestamp,
    StatusNotification201EvseConnectorIds,
]
