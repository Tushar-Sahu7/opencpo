"""
OCPP 2.0.1 message definitions and schemas.
Standalone — no external OCPP library dependencies.
"""

# Message type IDs (same as 1.6)
CALL = 2
CALL_RESULT = 3
CALL_ERROR = 4

# Valid OCPP 2.0.1 actions (charger → CSMS)
CHARGER_ACTIONS = {
    "BootNotification",
    "Heartbeat",
    "StatusNotification",
    "Authorize",
    "TransactionEvent",
    "MeterValues",
    "ReportChargingProfiles",
    "NotifyChargingLimit",
    "NotifyEVChargingNeeds",
    "NotifyEVChargingSchedule",
    "SecurityEventNotification",
    "SignCertificate",
    "Get15118EVCertificate",
    "GetCertificateStatus",
    "NotifyReport",
    "NotifyDisplayMessages",
    "NotifyCustomerInformation",
    "LogStatusNotification",
    "FirmwareStatusNotification",
    "PublishFirmwareStatusNotification",
    "DataTransfer",
}

# Valid OCPP 2.0.1 actions (CSMS → charger)
CSMS_ACTIONS = {
    "CancelReservation",
    "CertificateSigned",
    "ChangeAvailability",
    "ClearCache",
    "ClearChargingProfile",
    "ClearDisplayMessage",
    "ClearVariableMonitoring",
    "CostUpdated",
    "CustomerInformation",
    "DataTransfer",
    "DeleteCertificate",
    "GetBaseReport",
    "GetChargingProfiles",
    "GetCompositeSchedule",
    "GetDisplayMessages",
    "GetInstalledCertificateIds",
    "GetLocalListVersion",
    "GetLog",
    "GetMonitoringReport",
    "GetReport",
    "GetTransactionStatus",
    "GetVariables",
    "InstallCertificate",
    "PublishFirmware",
    "RequestStartTransaction",
    "RequestStopTransaction",
    "ReserveNow",
    "Reset",
    "SendLocalList",
    "SetChargingProfile",
    "SetDisplayMessage",
    "SetMonitoringBase",
    "SetMonitoringLevel",
    "SetNetworkProfile",
    "SetVariableMonitoring",
    "SetVariables",
    "TriggerMessage",
    "UnlockConnector",
    "UnpublishFirmware",
    "UpdateFirmware",
}

# Registration status
REGISTRATION_STATUS = {"Accepted", "Pending", "Rejected"}

# Authorization status
AUTHORIZATION_STATUS = {
    "Accepted", "Blocked", "ConcurrentTx", "Expired", "Invalid",
    "NoCredit", "NotAllowedTypeEVSE", "NotAtThisLocation",
    "NotAtThisTime", "Unknown"
}

# Connector status (2.0.1 — per EVSE)
CONNECTOR_STATUS = {
    "Available", "Occupied", "Reserved", "Unavailable", "Faulted"
}

# Transaction event types
TRANSACTION_EVENT = {"Started", "Updated", "Ended"}

# Stop reason for 2.0.1
STOP_REASONS = {
    "DeAuthorized", "EmergencyStop", "EnergyLimitReached", "EVDisconnected",
    "GroundFault", "ImmediateReset", "Local", "LocalOutOfCredit", "MasterPass",
    "Other", "OvercurrentFault", "PowerLoss", "PowerQuality", "Reboot",
    "Remote", "SOCLimitReached", "StoppedByEV", "TimeLimitReached", "Timeout"
}

# Trigger reason for TransactionEvent
TRIGGER_REASON = {
    "Authorized", "CablePluggedIn", "ChargingRateChanged", "ChargingStateChanged",
    "Deauthorized", "EnergyLimitReached", "EVCommunicationLost", "EVConnectTimeout",
    "MeterValueClock", "MeterValuePeriodic", "TimeLimitReached", "Trigger",
    "UnlockCommand", "StopAuthorized", "EVDeparted", "EVDetected",
    "RemoteStop", "RemoteStart", "AbnormalCondition", "SignedDataReceived",
    "ResetCommand"
}

# Charging state
CHARGING_STATE = {"Charging", "EVConnected", "SuspendedEV", "SuspendedEVSE", "Idle"}

# SetVariables status
SET_VARIABLE_STATUS = {
    "Accepted", "Rejected", "UnknownComponent", "UnknownVariable",
    "NotSupportedAttributeType", "RebootRequired"
}

# GetVariables status
GET_VARIABLE_STATUS = {
    "Accepted", "Rejected", "UnknownComponent", "UnknownVariable",
    "NotSupportedAttributeType"
}

# Security event type
SECURITY_EVENTS = {
    "FirmwareUpdated", "FailedToAuthenticateAtCsms", "CsmsAuthenticationFailed",
    "SettingSystemTime", "StartupOfTheDevice", "ResetOrReboot",
    "SecurityLogWasCleared", "ReconfigurationOfSecurityParameters",
    "MemoryExhaustion", "InvalidMessages", "AttemptedReplayAttacks",
    "TamperDetectionActivated", "InvalidFirmwareSignature",
    "InvalidFirmwareSigningCertificate", "InvalidCsmsCertificate",
    "InvalidChargePointCertificate", "InvalidTLSVersion",
    "InvalidTLSCipherSuite"
}

# Certificate types
CERTIFICATE_TYPES = {
    "ChargingStationCertificate", "V2GCertificate"
}

# OCPP CallError codes (same as 1.6)
CALL_ERROR_CODES = {
    "NotImplemented", "NotSupported", "InternalError", "ProtocolError",
    "SecurityError", "FormationViolation", "PropertyConstraintViolation",
    "OccurrenceConstraintViolation", "TypeConstraintViolation", "GenericError",
    "MessageTypeNotSupported", "FormatViolation",
}


def make_call(unique_id: str, action: str, payload: dict) -> list:
    return [CALL, unique_id, action, payload]


def make_result(unique_id: str, payload: dict) -> list:
    return [CALL_RESULT, unique_id, payload]


def make_error(unique_id: str, error_code: str, description: str = "", details: dict = None) -> list:
    return [CALL_ERROR, unique_id, error_code, description, details or {}]


def boot_notification_conf(status: str = "Accepted", interval: int = 30) -> dict:
    from datetime import datetime, timezone
    return {
        "currentTime": datetime.now(timezone.utc).isoformat(),
        "interval": interval,
        "status": status,
    }


def heartbeat_conf() -> dict:
    from datetime import datetime, timezone
    return {"currentTime": datetime.now(timezone.utc).isoformat()}


def status_notification_conf() -> dict:
    return {}


def authorize_conf(status: str = "Accepted") -> dict:
    return {"idTokenInfo": {"status": status}}


def transaction_event_conf() -> dict:
    return {}


def meter_values_conf() -> dict:
    return {}


def request_start_transaction_conf(status: str = "Accepted", transaction_id: str = None) -> dict:
    resp = {"status": status}
    if transaction_id:
        resp["transactionId"] = transaction_id
    return resp


def request_stop_transaction_conf(status: str = "Accepted") -> dict:
    return {"status": status}


def set_variables_conf(result: list = None) -> dict:
    return {"setVariableResult": result or []}


def get_variables_conf(result: list = None) -> dict:
    return {"getVariableResult": result or []}


def reset_conf(status: str = "Accepted") -> dict:
    return {"status": status}


def set_charging_profile_conf(status: str = "Accepted") -> dict:
    return {"status": status}


def clear_charging_profile_conf(status: str = "Accepted") -> dict:
    return {"status": status}


def get_charging_profiles_conf(status: str = "Accepted") -> dict:
    return {"status": status}


def get_base_report_conf(status: str = "Accepted") -> dict:
    return {"status": status}


def trigger_message_conf(status: str = "Accepted") -> dict:
    return {"status": status}
