"""
OCPP 1.6j message definitions and schemas.
Standalone — no external OCPP library dependencies.
"""

# Message type IDs
CALL = 2
CALL_RESULT = 3
CALL_ERROR = 4

# Valid OCPP 1.6 actions (charger → CSMS)
CHARGER_ACTIONS = {
    "BootNotification",
    "Heartbeat",
    "StatusNotification",
    "Authorize",
    "StartTransaction",
    "StopTransaction",
    "MeterValues",
    "DiagnosticsStatusNotification",
    "FirmwareStatusNotification",
    "DataTransfer",
    "StopTransaction",
}

# Valid OCPP 1.6 actions (CSMS → charger)
CSMS_ACTIONS = {
    "ChangeAvailability",
    "ChangeConfiguration",
    "ClearCache",
    "ClearChargingProfile",
    "DataTransfer",
    "GetCompositeSchedule",
    "GetConfiguration",
    "GetDiagnostics",
    "GetLocalListVersion",
    "RemoteStartTransaction",
    "RemoteStopTransaction",
    "ReserveNow",
    "Reset",
    "SendLocalList",
    "SetChargingProfile",
    "TriggerMessage",
    "UnlockConnector",
    "UpdateFirmware",
}

# Registration status values
REGISTRATION_STATUS = {"Accepted", "Pending", "Rejected"}

# Authorization status values
AUTHORIZATION_STATUS = {"Accepted", "Blocked", "Expired", "Invalid", "ConcurrentTx"}

# Connector status values
CONNECTOR_STATUS = {
    "Available", "Preparing", "Charging", "SuspendedEV",
    "SuspendedEVSE", "Finishing", "Reserved", "Unavailable", "Faulted"
}

# Error code values
ERROR_CODES = {
    "ConnectorLockFailure", "EVCommunicationError", "GroundFailure",
    "HighTemperature", "InternalError", "LocalListConflict", "NoError",
    "OtherError", "OverCurrentFailure", "OverVoltage", "PowerMeterFailure",
    "PowerSwitchFailure", "ReaderFailure", "ResetFailure", "UnderVoltage", "WeakSignal"
}

# Stop reason values
STOP_REASONS = {
    "EmergencyStop", "EVDisconnected", "HardReset", "Local", "Other",
    "PowerLoss", "Reboot", "Remote", "SoftReset", "UnlockCommand", "DeAuthorized"
}

# OCPP CallError codes
CALL_ERROR_CODES = {
    "NotImplemented", "NotSupported", "InternalError", "ProtocolError",
    "SecurityError", "FormationViolation", "PropertyConstraintViolation",
    "OccurrenceConstraintViolation", "TypeConstraintViolation", "GenericError"
}

# Measurand values
MEASURANDS = {
    "Energy.Active.Export.Interval",
    "Energy.Active.Export.Register",
    "Energy.Active.Import.Interval",
    "Energy.Active.Import.Register",
    "Energy.Reactive.Export.Interval",
    "Energy.Reactive.Export.Register",
    "Energy.Reactive.Import.Interval",
    "Energy.Reactive.Import.Register",
    "Power.Active.Export",
    "Power.Active.Import",
    "Power.Factor",
    "Power.Offered",
    "Power.Reactive.Export",
    "Power.Reactive.Import",
    "Current.Export",
    "Current.Import",
    "Current.Offered",
    "Voltage",
    "Frequency",
    "Temperature",
    "SoC",
    "RPM",
}

# Unit values per measurand
MEASURAND_UNITS = {
    "Energy.Active.Import.Register": {"Wh", "kWh"},
    "Energy.Active.Export.Register": {"Wh", "kWh"},
    "Energy.Active.Import.Interval": {"Wh", "kWh"},
    "Energy.Active.Export.Interval": {"Wh", "kWh"},
    "Energy.Reactive.Import.Register": {"varh", "kvarh"},
    "Energy.Reactive.Export.Register": {"varh", "kvarh"},
    "Power.Active.Import": {"W", "kW"},
    "Power.Active.Export": {"W", "kW"},
    "Power.Reactive.Import": {"var", "kvar"},
    "Power.Reactive.Export": {"var", "kvar"},
    "Current.Import": {"A"},
    "Current.Export": {"A"},
    "Current.Offered": {"A"},
    "Voltage": {"V"},
    "Frequency": {"Hz"},
    "Temperature": {"Celsius", "Fahrenheit", "K"},
    "SoC": {"Percent"},
}

# Phase values
PHASES = {"L1", "L2", "L3", "N", "L1-N", "L2-N", "L3-N", "L1-L2", "L2-L3", "L3-L1"}

# Location values
LOCATIONS = {"Body", "Cable", "EV", "Inlet", "Outlet"}

# Format values
FORMATS = {"Raw", "SignedData"}

# Context values
CONTEXTS = {
    "Interruption.Begin", "Interruption.End", "Sample.Clock",
    "Sample.Periodic", "Transaction.Begin", "Transaction.End",
    "Trigger", "Other"
}

# ChargingProfileKindType
CHARGING_PROFILE_KIND = {"Absolute", "Recurring", "Relative"}

# ChargingProfilePurposeType
CHARGING_PROFILE_PURPOSE = {"ChargePointMaxProfile", "TxDefaultProfile", "TxProfile"}

# ChargingRateUnitType
CHARGING_RATE_UNIT = {"W", "A"}

# RecurrencyKindType
RECURRENCY_KIND = {"Daily", "Weekly"}

# Reset type
RESET_TYPE = {"Hard", "Soft"}

# Availability type
AVAILABILITY_TYPE = {"Inoperative", "Operative"}

# TriggerMessage types
TRIGGER_MESSAGE_TYPES = {
    "BootNotification", "DiagnosticsStatusNotification", "FirmwareStatusNotification",
    "Heartbeat", "MeterValues", "StatusNotification"
}

# FirmwareStatus
FIRMWARE_STATUS = {"Downloaded", "DownloadFailed", "Downloading", "Idle", "InstallationFailed", "Installed", "Installing"}

# DiagnosticsStatus
DIAGNOSTICS_STATUS = {"Idle", "Uploaded", "UploadFailed", "Uploading"}

# Field length limits per OCPP 1.6 spec
FIELD_LENGTHS = {
    "chargePointVendor": 20,
    "chargePointModel": 20,
    "chargePointSerialNumber": 25,
    "chargeBoxSerialNumber": 25,
    "firmwareVersion": 50,
    "iccid": 20,
    "imsi": 20,
    "meterType": 25,
    "meterSerialNumber": 25,
    "idTag": 20,
    "parentIdTag": 20,
    "vendorId": 255,
    "vendorErrorCode": 50,
    "info": 50,
}

# Well-known configuration keys
STANDARD_CONFIG_KEYS = {
    "AllowOfflineTxForUnknownId",
    "AuthorizationCacheEnabled",
    "AuthorizeRemoteTxRequests",
    "BlinkRepeat",
    "ClockAlignedDataInterval",
    "ConnectionTimeOut",
    "ConnectorPhaseRotation",
    "ConnectorPhaseRotationMaxLength",
    "GetConfigurationMaxKeys",
    "HeartbeatInterval",
    "LightIntensity",
    "LocalAuthListEnabled",
    "LocalAuthListMaxLength",
    "LocalAuthorizeOffline",
    "LocalPreAuthorize",
    "MaxEnergyOnInvalidId",
    "MeterValuesAlignedData",
    "MeterValuesAlignedDataMaxLength",
    "MeterValuesSampledData",
    "MeterValuesSampledDataMaxLength",
    "MeterValueSampleInterval",
    "MinimumStatusDuration",
    "NumberOfConnectors",
    "ResetRetries",
    "SendLocalListMaxLength",
    "StopTransactionMaxMeterValues",
    "StopTransactionOnEVSideDisconnect",
    "StopTransactionOnInvalidId",
    "StopTxnAlignedData",
    "StopTxnAlignedDataMaxLength",
    "StopTxnSampledData",
    "StopTxnSampledDataMaxLength",
    "SupportedFeatureProfiles",
    "TransactionMessageAttempts",
    "TransactionMessageRetryInterval",
    "UnlockConnectorOnEVSideDisconnect",
    "WebSocketPingInterval",
}


def make_call(unique_id: str, action: str, payload: dict) -> list:
    """Create an OCPP CALL message."""
    return [CALL, unique_id, action, payload]


def make_result(unique_id: str, payload: dict) -> list:
    """Create an OCPP CALL_RESULT message."""
    return [CALL_RESULT, unique_id, payload]


def make_error(unique_id: str, error_code: str, description: str = "", details: dict = None) -> list:
    """Create an OCPP CALL_ERROR message."""
    return [CALL_ERROR, unique_id, error_code, description, details or {}]


def boot_notification_conf(status: str = "Accepted", interval: int = 30) -> dict:
    """Build BootNotification.conf payload."""
    from datetime import datetime, timezone
    return {
        "currentTime": datetime.now(timezone.utc).isoformat(),
        "interval": interval,
        "status": status,
    }


def heartbeat_conf() -> dict:
    """Build Heartbeat.conf payload."""
    from datetime import datetime, timezone
    return {"currentTime": datetime.now(timezone.utc).isoformat()}


def status_notification_conf() -> dict:
    return {}


def authorize_conf(status: str = "Accepted") -> dict:
    return {"idTagInfo": {"status": status}}


def start_transaction_conf(transaction_id: int, status: str = "Accepted") -> dict:
    return {
        "transactionId": transaction_id,
        "idTagInfo": {"status": status},
    }


def stop_transaction_conf(status: str = "Accepted") -> dict:
    return {"idTagInfo": {"status": status}}


def meter_values_conf() -> dict:
    return {}


def get_configuration_conf(config_key: list = None, unknown_key: list = None) -> dict:
    return {
        "configurationKey": config_key or [],
        "unknownKey": unknown_key or [],
    }


def change_configuration_conf(status: str = "Accepted") -> dict:
    return {"status": status}


def remote_start_transaction_conf(status: str = "Accepted") -> dict:
    return {"status": status}


def remote_stop_transaction_conf(status: str = "Accepted") -> dict:
    return {"status": status}


def reset_conf(status: str = "Accepted") -> dict:
    return {"status": status}


def unlock_connector_conf(status: str = "Unlocked") -> dict:
    return {"status": status}


def set_charging_profile_conf(status: str = "Accepted") -> dict:
    return {"status": status}


def clear_charging_profile_conf(status: str = "Accepted") -> dict:
    return {"status": status}


def get_composite_schedule_conf(status: str = "Accepted", connector_id: int = 1,
                                 schedule_start: str = None, charging_schedule: dict = None) -> dict:
    return {
        "status": status,
        "connectorId": connector_id,
        "scheduleStart": schedule_start,
        "chargingSchedule": charging_schedule,
    }


def trigger_message_conf(status: str = "Accepted") -> dict:
    return {"status": status}


def update_firmware_conf() -> dict:
    return {}


def get_diagnostics_conf(file_name: str = None) -> dict:
    return {"fileName": file_name}


def get_local_list_version_conf(version: int = 0) -> dict:
    return {"listVersion": version}


def send_local_list_conf(status: str = "Accepted") -> dict:
    return {"status": status}
