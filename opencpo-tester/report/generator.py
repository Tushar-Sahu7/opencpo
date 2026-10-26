"""
Report data collector and aggregator.
Collects all TestResults and builds a structured report dict for PDF/HTML output.
"""
import json
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Any

from tests.base import TestResult, TestStatus, Severity


GRADE_COLORS = {
    "A+": "#16a34a", "A": "#22c55e",
    "B": "#84cc16",
    "C": "#f59e0b",
    "D": "#f97316",
    "F": "#dc2626",
}

GRADE_THRESHOLDS = [
    (98, "A+", "Excellent — Production Ready"),
    (90, "A",  "Very Good — Minor Issues"),
    (80, "B",  "Good — Some Fixes Needed"),
    (65, "C",  "Fair — Multiple Issues"),
    (50, "D",  "Poor — Significant Failures"),
    (0,  "F",  "Fail — Not Compliant"),
]


def calculate_grade(pass_pct: float) -> tuple[str, str]:
    for threshold, grade, label in GRADE_THRESHOLDS:
        if pass_pct >= threshold:
            return grade, label
    return "F", "Fail — Not Compliant"


@dataclass
class CategorySummary:
    name: str
    display_name: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    critical_failures: int = 0
    warning_failures: int = 0

    @property
    def pass_pct(self) -> float:
        effective = self.total - self.skipped
        if effective == 0:
            return 100.0
        return (self.passed / effective) * 100

    @property
    def has_critical_failure(self) -> bool:
        return self.critical_failures > 0


@dataclass
class ReportData:
    """Complete report data structure passed to PDF/HTML generators."""

    # Report metadata
    title: str = "OCPP Compliance Test Report"
    company: str = "OCPP Compliance Tester"
    generated_at: str = ""

    # Charger details
    charger_id: str = ""
    charger_vendor: str = ""
    charger_model: str = ""
    charger_serial: str = ""
    charger_firmware: str = ""
    ocpp_version: str = ""
    test_date: str = ""

    # Summary stats
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    error_tests: int = 0
    pass_percentage: float = 0.0
    grade: str = "F"
    grade_label: str = ""

    # Category summaries
    categories: list[CategorySummary] = field(default_factory=list)

    # All test results
    results: list[TestResult] = field(default_factory=list)

    # Failed results only (for deviation section)
    failures: list[TestResult] = field(default_factory=list)

    # Full message log
    message_log: list[dict] = field(default_factory=list)

    # Recommendations (auto-generated from failures)
    recommendations: list[str] = field(default_factory=list)

    # Test criteria & spec references
    test_criteria: list[dict] = field(default_factory=list)

    # Branding settings (colors, logo, company)
    branding: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        """Serialize report to a complete JSON-serializable dict for dashboard consumption."""
        # Serialize categories
        categories_out = []
        for cat in self.categories:
            categories_out.append({
                "name": cat.name,
                "display_name": cat.display_name,
                "total": cat.total,
                "passed": cat.passed,
                "failed": cat.failed,
                "skipped": cat.skipped,
                "errors": cat.errors,
                "critical_failures": cat.critical_failures,
                "warning_failures": cat.warning_failures,
                "pass_pct": round(cat.pass_pct, 1),
                "has_critical_failure": cat.has_critical_failure,
            })

        # Serialize all test results
        results_out = []
        for r in self.results:
            results_out.append({
                "name": getattr(r, "test_name", str(r)),
                "category": getattr(r, "category", ""),
                "status": r.status.value if hasattr(r.status, "value") else str(r.status),
                "severity": r.severity.value if hasattr(r.severity, "value") else str(r.severity),
                "message": getattr(r, "message", ""),
                "spec_ref": getattr(r, "spec_ref", ""),
                "fix_recommendation": getattr(r, "fix_recommendation", ""),
                "duration_ms": getattr(r, "duration_ms", None),
            })

        # Critical failures only
        critical_failures_out = []
        for r in self.results:
            is_failed = getattr(r, "failed", False)
            sev = r.severity.value if hasattr(r.severity, "value") else str(r.severity)
            if is_failed and sev == "CRITICAL":
                critical_failures_out.append({
                    "name": getattr(r, "test_name", str(r)),
                    "category": getattr(r, "category", ""),
                    "message": getattr(r, "message", ""),
                    "spec_ref": getattr(r, "spec_ref", ""),
                    "fix_recommendation": getattr(r, "fix_recommendation", ""),
                })

        return {
            "generated_at": self.generated_at,
            "title": self.title,
            "company": self.company,
            "grade": self.grade,
            "grade_label": self.grade_label,
            "pass_percentage": round(self.pass_percentage, 1),
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "skipped_tests": self.skipped_tests,
            "error_tests": self.error_tests,
            "charger": {
                "id": self.charger_id,
                "vendor": self.charger_vendor,
                "model": self.charger_model,
                "serial": self.charger_serial,
                "firmware": self.charger_firmware,
                "ocpp_version": self.ocpp_version,
            },
            "categories": categories_out,
            "results": results_out,
            "critical_failures": critical_failures_out,
            "recommendations": self.recommendations,
            "test_criteria": self.test_criteria,
        }


TEST_CRITERIA = [
    {
        "category": "boot",
        "display_name": "Connection & Boot Sequence",
        "spec_ref": "OCPP 1.6 §5.2, §5.5",
        "description": (
            "Validates the charger's WebSocket connection, BootNotification payload, "
            "and heartbeat timing after connection establishment."
        ),
        "pass_criteria": [
            "BootNotification must contain chargePointVendor and chargePointModel (required fields)",
            "CSMS responds with Accepted/Pending/Rejected and a valid heartbeatInterval",
            "Heartbeat messages must arrive within ±10% of the configured interval",
        ],
    },
    {
        "category": "status",
        "display_name": "Status Notifications",
        "spec_ref": "OCPP 1.6 §5.18",
        "description": (
            "Validates that the charger correctly reports connector status changes "
            "using well-defined enum values and valid timestamps."
        ),
        "pass_criteria": [
            "Charger must send StatusNotification for each connector after boot",
            "Status values must be from the defined enum (Available, Preparing, Charging, etc.)",
            "errorCode must be from the defined enum (NoError, GroundFailure, etc.)",
            "Timestamps must be valid ISO 8601 with timezone offset",
        ],
    },
    {
        "category": "protocol",
        "display_name": "Protocol Compliance",
        "spec_ref": "OCPP 1.6 §4",
        "description": (
            "Validates low-level OCPP protocol rules: WebSocket subprotocol, "
            "message framing, uniqueId uniqueness, and error handling."
        ),
        "pass_criteria": [
            "Messages must use the ocpp1.6 WebSocket subprotocol",
            "All messages must be valid JSON arrays: [messageTypeId, uniqueId, ...]",
            "uniqueId must be unique per session",
            "Unknown actions must receive CALL_ERROR (not CALL_RESULT)",
            "Malformed JSON must be handled gracefully without disconnecting",
            "No concurrent CALL messages — charger must wait for response",
        ],
    },
    {
        "category": "auth",
        "display_name": "Authorization",
        "spec_ref": "OCPP 1.6 §5.1",
        "description": (
            "Validates the Authorize request/response cycle, including idTag "
            "format and CSMS response structure."
        ),
        "pass_criteria": [
            "Authorize request contains a valid idTag (max 20 characters)",
            "CSMS responds with idTagInfo containing a status field",
        ],
    },
    {
        "category": "transactions",
        "display_name": "Transaction Management",
        "spec_ref": "OCPP 1.6 §5.16, §5.17",
        "description": (
            "Validates StartTransaction and StopTransaction message contents, "
            "meter value consistency, and transactionId tracking."
        ),
        "pass_criteria": [
            "StartTransaction must contain connectorId, idTag, meterStart, timestamp",
            "StopTransaction must contain meterStop, timestamp, transactionId",
            "meterStop must be >= meterStart",
            "transactionId must match the one from the StartTransaction response",
        ],
    },
    {
        "category": "meter_values",
        "display_name": "Meter Values",
        "spec_ref": "OCPP 1.6 §5.11",
        "description": (
            "Validates meter value samples for correct measurands, monotonically "
            "increasing timestamps, and parseable numeric values."
        ),
        "pass_criteria": [
            "MeterValues must contain valid measurand, value, and unit",
            "Energy.Active.Import.Register must be present and non-decreasing",
            "Timestamps must be monotonically increasing",
            "All values must be parseable as numbers",
        ],
    },
    {
        "category": "remote_control",
        "display_name": "Remote Control & Configuration",
        "spec_ref": "OCPP 1.6 §5.4, §5.6, §5.7, §5.9, §5.15, §5.19, §5.20",
        "description": (
            "Validates charger responses to CSMS-initiated commands including Reset, "
            "ChangeConfiguration, GetConfiguration, and TriggerMessage."
        ),
        "pass_criteria": [
            "Reset (Soft/Hard) must return Accepted",
            "ChangeConfiguration for known keys returns Accepted or RebootRequired",
            "ChangeConfiguration for unknown keys returns NotSupported",
            "GetConfiguration returns all supported keys",
            "TriggerMessage triggers the requested message type",
        ],
    },
    {
        "category": "smart_charging",
        "display_name": "Smart Charging",
        "spec_ref": "OCPP 1.6 §5.8, §5.3, §5.10",
        "description": (
            "Validates SetChargingProfile, ClearChargingProfile, and "
            "GetCompositeSchedule command handling."
        ),
        "pass_criteria": [
            "SetChargingProfile with a valid profile returns Accepted",
            "Invalid charging profiles return Rejected",
            "ClearChargingProfile returns Accepted",
            "GetCompositeSchedule returns a valid schedule",
        ],
    },
    {
        "category": "firmware",
        "display_name": "Firmware & Diagnostics",
        "spec_ref": "OCPP 1.6 §5.21, §5.22",
        "description": (
            "Validates firmware update initiation and diagnostics upload flows, "
            "including status notification messages."
        ),
        "pass_criteria": [
            "UpdateFirmware is accepted and FirmwareStatusNotification is sent",
            "GetDiagnostics triggers DiagnosticsStatusNotification",
        ],
    },
]


CATEGORY_DISPLAY_NAMES = {
    "boot": "Connection & Boot Sequence",
    "status": "Status Notifications",
    "auth": "Authorization",
    "transactions": "Transaction Management",
    "meter_values": "Meter Values",
    "remote_control": "Remote Control & Configuration",
    "smart_charging": "Smart Charging",
    "firmware": "Firmware & Diagnostics",
    "protocol": "Protocol Compliance",
}


class ReportGenerator:
    """Aggregates test results into a ReportData object."""

    def __init__(self, config: dict = None):
        self.config = config or {}

    def build(self, results: list[TestResult], connection, message_log: list[dict] = None) -> ReportData:
        """Build report from test results and connection info."""
        now = datetime.now(timezone.utc)

        branding = self.config.get("branding", {})
        report = ReportData(
            company=branding.get("company", self.config.get("report", {}).get("company", "OCPP Compliance Tester")),
            generated_at=now.isoformat(),
            test_date=now.strftime("%B %d, %Y"),
        )

        # Attach branding settings for use by HTML/PDF generators
        report.branding = branding

        # Charger details from connection
        if connection:
            report.charger_id = connection.charger_id
            report.charger_vendor = connection.vendor or connection.boot_payload.get("chargePointVendor", "Unknown")
            report.charger_model = connection.model or connection.boot_payload.get("chargePointModel", "Unknown")
            report.charger_serial = connection.serial or connection.boot_payload.get("chargePointSerialNumber", "N/A")
            report.charger_firmware = connection.firmware or connection.boot_payload.get("firmwareVersion", "N/A")
            report.ocpp_version = connection.ocpp_version

        report.title = f"OCPP {report.ocpp_version} Compliance Report — {report.charger_vendor} {report.charger_model}"

        # Store results
        report.results = results
        report.failures = [r for r in results if r.failed or r.status.value == "ERROR"]

        # Aggregate stats
        report.total_tests = len(results)
        report.passed_tests = sum(1 for r in results if r.passed)
        report.failed_tests = sum(1 for r in results if r.failed)
        report.skipped_tests = sum(1 for r in results if r.skipped)
        report.error_tests = sum(1 for r in results if r.status.value == "ERROR")

        effective = report.total_tests - report.skipped_tests
        if effective > 0:
            report.pass_percentage = (report.passed_tests / effective) * 100
        else:
            report.pass_percentage = 100.0

        report.grade, report.grade_label = calculate_grade(report.pass_percentage)

        # Category summaries
        cat_map: dict[str, CategorySummary] = {}
        for r in results:
            cat = r.category
            if cat not in cat_map:
                display = CATEGORY_DISPLAY_NAMES.get(cat, cat.replace("_", " ").title())
                cat_map[cat] = CategorySummary(name=cat, display_name=display)
            s = cat_map[cat]
            s.total += 1
            if r.passed:
                s.passed += 1
            elif r.failed:
                s.failed += 1
                if r.severity == Severity.CRITICAL:
                    s.critical_failures += 1
                elif r.severity == Severity.WARNING:
                    s.warning_failures += 1
            elif r.skipped:
                s.skipped += 1
            else:
                s.errors += 1

        # Order categories consistently
        cat_order = ["boot", "status", "auth", "transactions", "meter_values",
                     "remote_control", "smart_charging", "firmware", "protocol"]
        ordered_cats = []
        for cat in cat_order:
            if cat in cat_map:
                ordered_cats.append(cat_map.pop(cat))
        ordered_cats.extend(cat_map.values())
        report.categories = ordered_cats

        # Build recommendations from critical/warning failures
        report.recommendations = self._generate_recommendations(report.failures)

        # Test criteria
        report.test_criteria = TEST_CRITERIA

        # Message log
        if message_log:
            report.message_log = message_log
        elif connection:
            report.message_log = connection.log.get_all()

        return report

    def _generate_recommendations(self, failures: list[TestResult]) -> list[str]:
        """Generate prioritized fix recommendations from failures."""
        critical = [r for r in failures if r.severity == Severity.CRITICAL]
        warnings = [r for r in failures if r.severity == Severity.WARNING]
        infos = [r for r in failures if r.severity == Severity.INFO]

        recs = []

        if critical:
            recs.append(f"CRITICAL ({len(critical)} issues — fix before deployment):")
            for r in critical:
                if r.fix_recommendation:
                    recs.append(f"  • [{r.test_name}] {r.fix_recommendation}")
                else:
                    recs.append(f"  • [{r.test_name}] {r.message}")

        if warnings:
            recs.append(f"\nWARNING ({len(warnings)} issues — fix for full compliance):")
            for r in warnings:
                if r.fix_recommendation:
                    recs.append(f"  • [{r.test_name}] {r.fix_recommendation}")
                else:
                    recs.append(f"  • [{r.test_name}] {r.message}")

        if infos:
            recs.append(f"\nINFO ({len(infos)} items — best practice improvements):")
            for r in infos:
                if r.fix_recommendation:
                    recs.append(f"  • [{r.test_name}] {r.fix_recommendation}")

        return recs
