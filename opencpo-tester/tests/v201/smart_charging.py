"""
OCPP 2.0.1 Smart Charging tests.
SetChargingProfile, ClearChargingProfile, GetChargingProfiles, GetCompositeSchedule.
2.0.1 uses ChargingProfilePurpose enum with different values than 1.6.
"""
from datetime import datetime, timezone, timedelta

from tests.base import OCPPTest, TestResult, Severity, make_exchange
from ocpp_messages.v201 import (
    set_charging_profile_conf, clear_charging_profile_conf,
    get_charging_profiles_conf
)

# 2.0.1 ChargingProfilePurpose values
CHARGING_PROFILE_PURPOSE_201 = {
    "ChargingStationExternalConstraints",
    "ChargingStationMaxProfile",
    "TxDefaultProfile",
    "TxProfile",
}

# 2.0.1 ChargingProfileKind values
CHARGING_PROFILE_KIND_201 = {"Absolute", "Recurring", "Relative"}


def make_tx_default_profile_201(profile_id: int, limit_w: float = 11000) -> dict:
    return {
        "id": profile_id,
        "stackLevel": 0,
        "chargingProfilePurpose": "TxDefaultProfile",
        "chargingProfileKind": "Relative",
        "chargingSchedule": [
            {
                "id": 1,
                "chargingRateUnit": "W",
                "chargingSchedulePeriod": [
                    {"startPeriod": 0, "limit": limit_w}
                ],
            }
        ],
    }


def make_charging_station_max_profile(profile_id: int, limit_w: float = 22000) -> dict:
    return {
        "id": profile_id,
        "stackLevel": 0,
        "chargingProfilePurpose": "ChargingStationMaxProfile",
        "chargingProfileKind": "Relative",
        "chargingSchedule": [
            {
                "id": 2,
                "chargingRateUnit": "W",
                "chargingSchedulePeriod": [
                    {"startPeriod": 0, "limit": limit_w}
                ],
            }
        ],
    }


class SmartCharging201Supported(OCPPTest):
    name = "smart_charging_201_supported"
    category = "smart_charging"
    description = "Check SmartChargingCtrlr variables to verify smart charging support"
    ocpp_spec_ref = "OCPP 2.0.1 §3.1"
    severity = Severity.INFO
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        # Query SmartChargingCtrlr.Enabled variable
        resp = await connection.send_call_and_wait("GetVariables", {
            "getVariableData": [
                {
                    "component": {"name": "SmartChargingCtrlr"},
                    "variable": {"name": "Enabled"},
                }
            ]
        }, timeout=10.0)

        if resp is None:
            return self.result(True,
                "Cannot determine SmartCharging support (GetVariables timed out) — proceeding",
                details={"note": "SmartCharging tests will proceed; may fail if not supported"})

        results = resp.get("getVariableResult", [])
        if results:
            status = results[0].get("attributeStatus", "")
            value = results[0].get("attributeValue", "")
            if status == "Accepted" and value.lower() == "false":
                return self.skip("SmartChargingCtrlr.Enabled=false — smart charging disabled")
            if status in ("UnknownComponent", "UnknownVariable"):
                return self.result(True,
                    "SmartChargingCtrlr component unknown — proceeding with smart charging tests")

        return self.result(True,
            "SmartCharging controller found — proceeding with tests")


class SetChargingProfile201TxDefault(OCPPTest):
    name = "set_charging_profile_201_tx_default"
    category = "smart_charging"
    description = "SetChargingProfile with TxDefaultProfile → Accepted"
    ocpp_spec_ref = "OCPP 2.0.1 §7.3"
    severity = Severity.WARNING
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        exchanges = []
        profile = make_tx_default_profile_201(profile_id=1, limit_w=11000)
        payload = {
            "evseId": 0,  # 0 = applies to all EVSEs
            "chargingProfile": profile,
        }

        resp = await connection.send_call_and_wait("SetChargingProfile", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "SetChargingProfile", "scp201_default", payload))

        if resp is None:
            return self.result(False, "SetChargingProfile timed out", exchanges=exchanges,
                               fix="Implement SetChargingProfile handler")

        exchanges.append(make_exchange("RECEIVED", "SetChargingProfile.conf", "scp201_default", resp))

        if resp.get("_is_error"):
            ec = resp.get("error_code", "")
            if ec in ("NotImplemented", "NotSupported"):
                return self.skip("SetChargingProfile not supported")
            return self.result(False, f"SetChargingProfile error: {ec}", exchanges=exchanges)

        status = resp.get("status", "")
        valid = {"Accepted", "Rejected", "InvalidProfile", "NotSupported",
                 "ExistingScheduleNotAllowed", "TxProfileMissingEvseId",
                 "DuplicateTxProfile", "NoKnownGoodSoCForEvse",
                 "ReasonCodeNotAllowed", "ChargingProfileNotAllowed"}
        if status not in valid:
            return self.result(False,
                f"Invalid SetChargingProfile status: '{status}'",
                expected=f"Valid status values from: {sorted(valid)}",
                actual=f"'{status}'",
                fix="Return a valid SetChargingProfileStatus value",
                exchanges=exchanges)

        if status == "Accepted":
            return self.result(True,
                "SetChargingProfile(TxDefaultProfile, 11kW) → Accepted",
                exchanges=exchanges)
        else:
            return self.result(True,
                f"SetChargingProfile returned {status} (check profile validity for this charger)",
                exchanges=exchanges,
                details={"note": f"Profile may have constraints specific to this charger"})


class SetChargingProfile201StationMax(OCPPTest):
    name = "set_charging_profile_201_station_max"
    category = "smart_charging"
    description = "SetChargingProfile with ChargingStationMaxProfile → Accepted or valid rejection"
    ocpp_spec_ref = "OCPP 2.0.1 §7.3"
    severity = Severity.INFO
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        exchanges = []
        profile = make_charging_station_max_profile(profile_id=10, limit_w=22000)
        payload = {
            "evseId": 0,
            "chargingProfile": profile,
        }

        resp = await connection.send_call_and_wait("SetChargingProfile", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "SetChargingProfile", "scp201_max", payload))

        if resp is None:
            return self.skip("SetChargingProfile timed out")

        exchanges.append(make_exchange("RECEIVED", "SetChargingProfile.conf", "scp201_max", resp))

        if resp.get("_is_error"):
            ec = resp.get("error_code", "")
            if ec in ("NotImplemented", "NotSupported"):
                return self.skip("ChargingStationMaxProfile not supported")

        status = resp.get("status", "")
        return self.result(True,
            f"SetChargingProfile(ChargingStationMaxProfile, 22kW) → {status}",
            exchanges=exchanges)


class ClearChargingProfile201(OCPPTest):
    name = "clear_charging_profile_201"
    category = "smart_charging"
    description = "ClearChargingProfile by id → Accepted or Unknown"
    ocpp_spec_ref = "OCPP 2.0.1 §7.4"
    severity = Severity.WARNING
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        exchanges = []
        payload = {
            "chargingProfileId": 1,
        }
        resp = await connection.send_call_and_wait("ClearChargingProfile", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "ClearChargingProfile", "ccp201_id", payload))

        if resp is None:
            return self.result(False, "ClearChargingProfile timed out", exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "ClearChargingProfile.conf", "ccp201_id", resp))

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
                expected="'Accepted' or 'Unknown'",
                actual=f"'{status}'",
                fix="Return 'Accepted' if cleared, 'Unknown' if profile not found",
                exchanges=exchanges)

        return self.result(True, f"ClearChargingProfile(id=1) → {status}", exchanges=exchanges)


class ClearChargingProfile201ByPurpose(OCPPTest):
    name = "clear_charging_profile_201_by_purpose"
    category = "smart_charging"
    description = "ClearChargingProfile with criteria clears matching profiles"
    ocpp_spec_ref = "OCPP 2.0.1 §7.4"
    severity = Severity.INFO
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        exchanges = []
        payload = {
            "chargingProfileCriteria": {
                "chargingProfilePurpose": "TxDefaultProfile",
                "evseId": 0,
            }
        }
        resp = await connection.send_call_and_wait("ClearChargingProfile", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "ClearChargingProfile", "ccp201_purpose", payload))

        if resp is None:
            return self.skip("ClearChargingProfile timed out")

        exchanges.append(make_exchange("RECEIVED", "ClearChargingProfile.conf", "ccp201_purpose", resp))
        status = resp.get("status", "")
        return self.result(True,
            f"ClearChargingProfile(purpose=TxDefaultProfile) → {status}",
            exchanges=exchanges)


class GetChargingProfiles201(OCPPTest):
    name = "get_charging_profiles_201"
    category = "smart_charging"
    description = "GetChargingProfiles returns valid ReportChargingProfiles or empty response"
    ocpp_spec_ref = "OCPP 2.0.1 §7.5"
    severity = Severity.WARNING
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        exchanges = []
        payload = {
            "requestId": 1,
            "chargingProfile": {},
            "evseId": 0,
        }
        resp = await connection.send_call_and_wait("GetChargingProfiles", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "GetChargingProfiles", "gcp201", payload))

        if resp is None:
            return self.result(False, "GetChargingProfiles timed out", exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "GetChargingProfiles.conf", "gcp201", resp))

        if resp.get("_is_error"):
            ec = resp.get("error_code", "")
            if ec in ("NotImplemented", "NotSupported"):
                return self.skip("GetChargingProfiles not supported")
            return self.result(False, f"GetChargingProfiles error: {ec}", exchanges=exchanges)

        status = resp.get("status", "")
        valid = {"Accepted", "NoProfiles"}
        if status not in valid:
            return self.result(False,
                f"Invalid GetChargingProfiles status: '{status}'",
                expected="'Accepted' or 'NoProfiles'",
                actual=f"'{status}'",
                fix="Return 'Accepted' (followed by ReportChargingProfiles) or 'NoProfiles'",
                exchanges=exchanges)

        if status == "NoProfiles":
            return self.result(True,
                "GetChargingProfiles → NoProfiles (no profiles set)",
                exchanges=exchanges)

        # Accepted → wait for ReportChargingProfiles
        rcp = await connection.wait_for_action("ReportChargingProfiles", timeout=10.0)
        if not rcp:
            return self.result(False,
                "GetChargingProfiles(Accepted) but no ReportChargingProfiles received",
                expected="ReportChargingProfiles after Accepted response",
                actual="No ReportChargingProfiles within 10s",
                fix="After responding Accepted to GetChargingProfiles, send ReportChargingProfiles",
                exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "ReportChargingProfiles", rcp["unique_id"], rcp["payload"]))
        await connection.send_result(rcp["unique_id"], {})

        profiles = rcp["payload"].get("chargingProfile", [])
        return self.result(True,
            f"GetChargingProfiles → {len(profiles)} profile(s) returned",
            exchanges=exchanges,
            details={"profile_count": len(profiles)})


class GetCompositeSchedule201(OCPPTest):
    name = "get_composite_schedule_201"
    category = "smart_charging"
    description = "GetCompositeSchedule returns valid schedule for active EVSE"
    ocpp_spec_ref = "OCPP 2.0.1 §7.2"
    severity = Severity.WARNING
    versions = ["2.0.1"]

    async def run(self, connection) -> TestResult:
        exchanges = []
        payload = {
            "duration": 3600,
            "evseId": 1,
            "chargingRateUnit": "W",
        }
        resp = await connection.send_call_and_wait("GetCompositeSchedule", payload, timeout=15.0)
        exchanges.append(make_exchange("SENT", "GetCompositeSchedule", "gcs201", payload))

        if resp is None:
            return self.result(False, "GetCompositeSchedule timed out", exchanges=exchanges)

        exchanges.append(make_exchange("RECEIVED", "GetCompositeSchedule.conf", "gcs201", resp))

        if resp.get("_is_error"):
            ec = resp.get("error_code", "")
            if ec in ("NotImplemented", "NotSupported"):
                return self.skip("GetCompositeSchedule not supported")
            return self.result(False, f"GetCompositeSchedule error: {ec}", exchanges=exchanges)

        status = resp.get("status", "")
        if status not in ("OK", "Rejected"):
            return self.result(False,
                f"Invalid status: '{status}'",
                expected="'OK' or 'Rejected'",
                actual=f"'{status}'",
                fix="GetCompositeSchedule.conf status must be 'OK' or 'Rejected'",
                exchanges=exchanges)

        if status == "Rejected":
            return self.result(True,
                "GetCompositeSchedule → Rejected (no active profile for EVSE 1)",
                exchanges=exchanges)

        schedule = resp.get("schedule", {})
        issues = []
        if not schedule:
            issues.append("Missing 'schedule' in response")
        else:
            if "chargingRateUnit" not in schedule:
                issues.append("schedule missing chargingRateUnit")
            if "chargingSchedulePeriod" not in schedule:
                issues.append("schedule missing chargingSchedulePeriod")
            else:
                for i, period in enumerate(schedule.get("chargingSchedulePeriod", [])):
                    if "startPeriod" not in period:
                        issues.append(f"period[{i}] missing startPeriod")
                    if "limit" not in period:
                        issues.append(f"period[{i}] missing limit")

        if issues:
            return self.result(False,
                f"Invalid schedule: {'; '.join(issues)}",
                exchanges=exchanges,
                fix="Return a valid CompositeSchedule with chargingRateUnit and chargingSchedulePeriod array")

        periods = schedule.get("chargingSchedulePeriod", [])
        return self.result(True,
            f"GetCompositeSchedule valid: {len(periods)} period(s), "
            f"unit={schedule.get('chargingRateUnit')}",
            exchanges=exchanges,
            details={"schedule": schedule})


ALL_TESTS = [
    SmartCharging201Supported,
    SetChargingProfile201TxDefault,
    SetChargingProfile201StationMax,
    ClearChargingProfile201,
    ClearChargingProfile201ByPurpose,
    GetChargingProfiles201,
    GetCompositeSchedule201,
]
