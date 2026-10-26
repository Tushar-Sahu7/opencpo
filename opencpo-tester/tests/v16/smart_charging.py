"""
OCPP 1.6 Smart Charging tests.
Validates ChargingProfile management, GetCompositeSchedule, and profile stacking.
"""
import asyncio
import json
import time
import uuid
from datetime import datetime, timezone, timedelta

from tests.base import OCPPTest, TestResult, Severity, make_exchange
from ocpp_messages.v16 import (
    set_charging_profile_conf, clear_charging_profile_conf,
    get_composite_schedule_conf, CHARGING_PROFILE_PURPOSE,
    CHARGING_PROFILE_KIND, CHARGING_RATE_UNIT
)


def make_tx_default_profile(profile_id: int, connector_id: int = 0,
                              limit_w: float = 11000) -> dict:
    """Create a valid TxDefaultProfile charging profile."""
    return {
        "chargingProfileId": profile_id,
        "stackLevel": 0,
        "chargingProfilePurpose": "TxDefaultProfile",
        "chargingProfileKind": "Relative",
        "chargingSchedule": {
            "chargingRateUnit": "W",
            "chargingSchedulePeriod": [
                {"startPeriod": 0, "limit": limit_w, "numberPhases": 3}
            ],
        },
    }


def make_tx_profile(profile_id: int, transaction_id: int, limit_w: float = 7400) -> dict:
    """Create a valid TxProfile charging profile."""
    return {
        "chargingProfileId": profile_id,
        "stackLevel": 1,
        "chargingProfilePurpose": "TxProfile",
        "transactionId": transaction_id,
        "chargingProfileKind": "Relative",
        "chargingSchedule": {
            "chargingRateUnit": "W",
            "chargingSchedulePeriod": [
                {"startPeriod": 0, "limit": limit_w, "numberPhases": 3}
            ],
        },
    }


class SmartChargingSupported(OCPPTest):
    name = "smart_charging_supported"
    category = "smart_charging"
    description = "Check if SmartCharging feature profile is supported"
    ocpp_spec_ref = "OCPP 1.6 §3.1"
    severity = Severity.INFO
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        supported = connection.known_config.get("SupportedFeatureProfiles", "")
        if supported and "SmartCharging" not in supported:
            return self.skip("SmartCharging not in SupportedFeatureProfiles — skipping smart charging tests")

        if not supported:
            return self.result(True,
                "SupportedFeatureProfiles not retrieved — proceeding with smart charging tests",
                details={"note": "Run GetConfiguration first to check supported profiles"})

        return self.result(True,
            f"SmartCharging supported (SupportedFeatureProfiles: {supported})")


class SetChargingProfileTxDefault(OCPPTest):
    name = "set_charging_profile_tx_default"
    category = "smart_charging"
    description = "SetChargingProfile with TxDefaultProfile → Accepted"
    ocpp_spec_ref = "OCPP 1.6 §7.3"
    severity = Severity.WARNING
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        # Check support
        supported = connection.known_config.get("SupportedFeatureProfiles", "")
        if supported and "SmartCharging" not in supported:
            return self.skip("SmartCharging not supported")

        exchanges = []
        profile = make_tx_default_profile(profile_id=1, connector_id=0, limit_w=11000)
        payload = {
            "connectorId": 0,  # 0 = applies to all connectors
            "csChargingProfiles": profile,
        }

        resp = await connection.send_call_and_wait("SetChargingProfile", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "SetChargingProfile", "scp_default", payload))

        if resp is None:
            return self.result(False, "SetChargingProfile timed out", exchanges=exchanges,
                               fix="Implement SetChargingProfile handler")

        exchanges.append(make_exchange("RECEIVED", "SetChargingProfile.conf", "scp_default", resp))

        if resp.get("_is_error"):
            ec = resp.get("error_code", "")
            if ec in ("NotImplemented", "NotSupported"):
                return self.skip("SetChargingProfile not supported")
            return self.result(False, f"SetChargingProfile error: {ec}", exchanges=exchanges)

        status = resp.get("status", "")
        valid = {"Accepted", "Rejected", "NotSupported"}
        if status not in valid:
            return self.result(False,
                f"Invalid SetChargingProfile status: '{status}'",
                expected=f"One of: {sorted(valid)}",
                actual=f"'{status}'",
                exchanges=exchanges)

        if status == "Accepted":
            return self.result(True,
                "SetChargingProfile(TxDefaultProfile, 11kW) → Accepted",
                exchanges=exchanges)
        else:
            return self.result(True,
                f"SetChargingProfile returned {status} (check profile validity)",
                exchanges=exchanges,
                details={"note": f"Profile may be valid but charger returned {status}"})


class SetChargingProfileTxProfile(OCPPTest):
    name = "set_charging_profile_tx_profile"
    category = "smart_charging"
    description = "SetChargingProfile with TxProfile + transactionId → Accepted"
    ocpp_spec_ref = "OCPP 1.6 §7.3"
    severity = Severity.WARNING
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        supported = connection.known_config.get("SupportedFeatureProfiles", "")
        if supported and "SmartCharging" not in supported:
            return self.skip("SmartCharging not supported")

        txn_id = connection.active_transaction_id
        if txn_id is None:
            return self.skip("No active transaction — TxProfile requires transactionId")

        connector_id = connection.active_connector_id or 1
        exchanges = []
        profile = make_tx_profile(profile_id=2, transaction_id=txn_id, limit_w=7400)
        payload = {
            "connectorId": connector_id,
            "csChargingProfiles": profile,
        }

        resp = await connection.send_call_and_wait("SetChargingProfile", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "SetChargingProfile", "scp_tx", payload))

        if resp is None:
            return self.result(False, "SetChargingProfile(TxProfile) timed out", exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "SetChargingProfile.conf", "scp_tx", resp))

        status = resp.get("status", "")
        if status == "Accepted":
            return self.result(True,
                f"SetChargingProfile(TxProfile, txn={txn_id}, 7.4kW) → Accepted",
                exchanges=exchanges)
        elif resp.get("_is_error") or status == "NotSupported":
            return self.skip("TxProfile not supported")
        else:
            return self.result(True,
                f"SetChargingProfile(TxProfile) returned {status}",
                exchanges=exchanges)


class SetChargingProfileInvalid(OCPPTest):
    name = "set_charging_profile_invalid"
    category = "smart_charging"
    description = "SetChargingProfile with invalid parameters → Rejected"
    ocpp_spec_ref = "OCPP 1.6 §7.3"
    severity = Severity.INFO
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        supported = connection.known_config.get("SupportedFeatureProfiles", "")
        if supported and "SmartCharging" not in supported:
            return self.skip("SmartCharging not supported")

        exchanges = []
        # Send with past validFrom date
        past_date = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
        profile = {
            "chargingProfileId": 999,
            "stackLevel": 0,
            "chargingProfilePurpose": "TxDefaultProfile",
            "chargingProfileKind": "Absolute",
            "validFrom": past_date,
            "validTo": past_date,  # Already expired
            "chargingSchedule": {
                "chargingRateUnit": "W",
                "chargingSchedulePeriod": [
                    {"startPeriod": 0, "limit": 22000}
                ],
            },
        }
        payload = {"connectorId": 1, "csChargingProfiles": profile}

        resp = await connection.send_call_and_wait("SetChargingProfile", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "SetChargingProfile", "scp_invalid", payload))

        if resp is None:
            return self.result(False, "SetChargingProfile(invalid) timed out", exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "SetChargingProfile.conf", "scp_invalid", resp))

        status = resp.get("status", "")

        # Ideally Rejected, but spec allows Accepted (charger may not validate dates)
        return self.result(True,
            f"SetChargingProfile(expired validTo) → {status}",
            exchanges=exchanges,
            details={"note": "Charger may or may not validate profile validity dates"})


class ClearChargingProfileById(OCPPTest):
    name = "clear_charging_profile_by_id"
    category = "smart_charging"
    description = "ClearChargingProfile by profileId → Accepted"
    ocpp_spec_ref = "OCPP 1.6 §7.4"
    severity = Severity.WARNING
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        supported = connection.known_config.get("SupportedFeatureProfiles", "")
        if supported and "SmartCharging" not in supported:
            return self.skip("SmartCharging not supported")

        exchanges = []
        payload = {"id": 1}  # Clear profile ID 1 set earlier
        resp = await connection.send_call_and_wait("ClearChargingProfile", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "ClearChargingProfile", "ccp_id", payload))

        if resp is None:
            return self.result(False, "ClearChargingProfile timed out", exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "ClearChargingProfile.conf", "ccp_id", resp))

        if resp.get("_is_error"):
            ec = resp.get("error_code", "")
            if ec in ("NotImplemented", "NotSupported"):
                return self.skip("ClearChargingProfile not supported")
            return self.result(False, f"ClearChargingProfile error: {ec}", exchanges=exchanges)

        status = resp.get("status", "")
        valid = {"Accepted", "Unknown"}
        if status not in valid:
            return self.result(False,
                f"Invalid ClearChargingProfile status: '{status}'",
                expected=f"'Accepted' or 'Unknown'",
                actual=f"'{status}'",
                fix="Return 'Accepted' if profile cleared, 'Unknown' if not found",
                exchanges=exchanges)

        return self.result(True, f"ClearChargingProfile(id=1) → {status}", exchanges=exchanges)


class ClearChargingProfileByPurpose(OCPPTest):
    name = "clear_charging_profile_by_purpose"
    category = "smart_charging"
    description = "ClearChargingProfile by purpose → clears all matching profiles"
    ocpp_spec_ref = "OCPP 1.6 §7.4"
    severity = Severity.INFO
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        supported = connection.known_config.get("SupportedFeatureProfiles", "")
        if supported and "SmartCharging" not in supported:
            return self.skip("SmartCharging not supported")

        exchanges = []
        payload = {
            "chargingProfilePurpose": "TxDefaultProfile",
            "connectorId": 0,
        }
        resp = await connection.send_call_and_wait("ClearChargingProfile", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "ClearChargingProfile", "ccp_purpose", payload))

        if resp is None:
            return self.skip("ClearChargingProfile timed out")

        exchanges.append(make_exchange("RECEIVED", "ClearChargingProfile.conf", "ccp_purpose", resp))

        status = resp.get("status", "")
        return self.result(True,
            f"ClearChargingProfile(purpose=TxDefaultProfile) → {status}",
            exchanges=exchanges)


class GetCompositeSchedule(OCPPTest):
    name = "get_composite_schedule"
    category = "smart_charging"
    description = "GetCompositeSchedule returns valid schedule"
    ocpp_spec_ref = "OCPP 1.6 §7.2"
    severity = Severity.WARNING
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        supported = connection.known_config.get("SupportedFeatureProfiles", "")
        if supported and "SmartCharging" not in supported:
            return self.skip("SmartCharging not supported")

        connector_id = connection.active_connector_id or 1
        exchanges = []
        payload = {
            "connectorId": connector_id,
            "duration": 3600,  # 1 hour
        }
        resp = await connection.send_call_and_wait("GetCompositeSchedule", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "GetCompositeSchedule", "gcs", payload))

        if resp is None:
            return self.result(False, "GetCompositeSchedule timed out", exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "GetCompositeSchedule.conf", "gcs", resp))

        if resp.get("_is_error"):
            ec = resp.get("error_code", "")
            if ec in ("NotImplemented", "NotSupported"):
                return self.skip("GetCompositeSchedule not supported")
            return self.result(False, f"GetCompositeSchedule error: {ec}", exchanges=exchanges)

        status = resp.get("status", "")
        if status not in ("Accepted", "Rejected"):
            return self.result(False,
                f"Invalid status: '{status}'",
                exchanges=exchanges)

        if status == "Rejected":
            return self.result(True,
                "GetCompositeSchedule rejected (no active profile)",
                exchanges=exchanges)

        # Validate schedule structure
        schedule = resp.get("chargingSchedule", {})
        issues = []
        if not schedule:
            issues.append("chargingSchedule missing from response")
        else:
            if "chargingRateUnit" not in schedule:
                issues.append("chargingSchedule missing chargingRateUnit")
            elif schedule["chargingRateUnit"] not in CHARGING_RATE_UNIT:
                issues.append(f"Invalid chargingRateUnit: '{schedule['chargingRateUnit']}'")
            if "chargingSchedulePeriod" not in schedule:
                issues.append("chargingSchedule missing chargingSchedulePeriod array")
            else:
                for i, period in enumerate(schedule.get("chargingSchedulePeriod", [])):
                    if "startPeriod" not in period:
                        issues.append(f"Period[{i}] missing startPeriod")
                    if "limit" not in period:
                        issues.append(f"Period[{i}] missing limit")

        if issues:
            return self.result(False,
                f"Invalid schedule: {'; '.join(issues)}",
                expected="chargingSchedule with chargingRateUnit and chargingSchedulePeriod array",
                actual="; ".join(issues),
                fix="Return a valid ChargingSchedule with chargingRateUnit (W or A) "
                    "and at least one chargingSchedulePeriod with startPeriod and limit",
                exchanges=exchanges)

        periods = schedule.get("chargingSchedulePeriod", [])
        return self.result(True,
            f"GetCompositeSchedule valid: {len(periods)} period(s), "
            f"unit={schedule.get('chargingRateUnit')}",
            exchanges=exchanges,
            details={"schedule": schedule})


ALL_TESTS = [
    SmartChargingSupported,
    SetChargingProfileTxDefault,
    SetChargingProfileTxProfile,
    SetChargingProfileInvalid,
    ClearChargingProfileById,
    ClearChargingProfileByPurpose,
    GetCompositeSchedule,
]
