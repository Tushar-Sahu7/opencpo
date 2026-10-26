"""
OCPP Compliance Test Runner / Orchestrator.

Runs tests in dependency order, handles timeouts, interactive prompts,
auto-responds to charger messages during tests, and collects results.
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.table import Table as RichTable
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Confirm, Prompt

from server import OCPPServer, ChargerConnection
from tests.base import OCPPTest, TestResult, TestStatus, Severity
from ocpp_messages import v16 as msg16
from ocpp_messages import v201 as msg201

logger = logging.getLogger(__name__)
console = Console()

# ── Test Registry ─────────────────────────────────────────────────────────

# OCPP 1.6 tests
from tests.v16.boot import ALL_TESTS as BOOT_16
from tests.v16.status import ALL_TESTS as STATUS_16
from tests.v16.auth import ALL_TESTS as AUTH_16
from tests.v16.transactions import ALL_TESTS as TXN_16
from tests.v16.meter_values import ALL_TESTS as METER_16
from tests.v16.remote_control import ALL_TESTS as REMOTE_16
from tests.v16.smart_charging import ALL_TESTS as SMART_16
from tests.v16.firmware import ALL_TESTS as FW_16
from tests.v16.protocol import ALL_TESTS as PROTO_16

# OCPP 2.0.1 tests
from tests.v201.boot import ALL_TESTS as BOOT_201
from tests.v201.status import ALL_TESTS as STATUS_201
from tests.v201.transactions import ALL_TESTS as TXN_201
from tests.v201.variables import ALL_TESTS as VAR_201
from tests.v201.protocol import ALL_TESTS as PROTO_201


V16_TEST_CATEGORIES = {
    "boot": BOOT_16,
    "status": STATUS_16,
    "auth": AUTH_16,
    "transactions": TXN_16,
    "meter_values": METER_16,
    "remote_control": REMOTE_16,
    "smart_charging": SMART_16,
    "firmware": FW_16,
    "protocol": PROTO_16,
}

V201_TEST_CATEGORIES = {
    "boot": BOOT_201,
    "status": STATUS_201,
    "transactions": TXN_201,
    "remote_control": VAR_201,
    "protocol": PROTO_201,
}

# Default test order — dependencies flow left to right
DEFAULT_CATEGORY_ORDER = [
    "boot", "protocol", "status", "remote_control",
    "auth", "transactions", "meter_values",
    "smart_charging", "firmware",
]

# Non-default tests (only run with --full)
FULL_ONLY_CATEGORIES = {"firmware"}


class TestRunner:
    """Orchestrates OCPP compliance test execution."""

    def __init__(self, config: dict):
        self.config = config
        self.results: list[TestResult] = []
        self.interactive = config.get("interactive", config.get("tests", {}).get("interactive", True))
        self.timeout = config.get("timing", {}).get("test_timeout", 120)
        self._connection: Optional[ChargerConnection] = None
        self._server: Optional[OCPPServer] = None

    async def run_all(self, server: OCPPServer, connection: ChargerConnection,
                       categories: list[str] = None, skip: list[str] = None,
                       full: bool = False) -> list[TestResult]:
        """Run all applicable tests and return results."""
        self._server = server
        self._connection = connection

        # Determine OCPP version
        version = connection.ocpp_version
        if version == "2.0.1":
            test_registry = V201_TEST_CATEGORIES
        else:
            test_registry = V16_TEST_CATEGORIES

        # Determine categories to run
        skip_set = set(skip or [])
        if not full:
            skip_set |= FULL_ONLY_CATEGORIES

        if categories:
            run_categories = [c for c in DEFAULT_CATEGORY_ORDER if c in categories and c not in skip_set]
        else:
            run_categories = [c for c in DEFAULT_CATEGORY_ORDER if c not in skip_set]

        console.print()
        console.print(Panel(
            f"[bold cyan]OCPP {version} Compliance Test Suite[/]\n"
            f"Charger: [bold]{connection.charger_id}[/]\n"
            f"Vendor: {connection.vendor or connection.boot_payload.get('chargePointVendor', '?')}\n"
            f"Model: {connection.model or connection.boot_payload.get('chargePointModel', '?')}\n"
            f"Firmware: {connection.firmware or connection.boot_payload.get('firmwareVersion', '?')}\n"
            f"Categories: {', '.join(run_categories)}\n"
            f"Interactive: {'Yes' if self.interactive else 'No'}",
            title="🔌 OCPP Tester",
            border_style="blue",
        ))

        total_tests = sum(
            len(test_registry.get(cat, []))
            for cat in run_categories
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            overall = progress.add_task(f"Running {total_tests} tests...", total=total_tests)

            for cat in run_categories:
                test_classes = test_registry.get(cat, [])
                if not test_classes:
                    continue

                progress.update(overall, description=f"[bold cyan]{cat}[/] ({len(test_classes)} tests)")

                for test_cls in test_classes:
                    test = test_cls(self.config)

                    # Check version compatibility
                    if version not in test.versions:
                        self.results.append(test.skip(f"Not applicable to OCPP {version}"))
                        progress.advance(overall)
                        continue

                    # Check interactive requirement
                    if test.interactive and not self.interactive:
                        self.results.append(test.skip("Requires --interactive mode"))
                        progress.advance(overall)
                        continue

                    # Interactive prompt if needed
                    if test.interactive and self.interactive:
                        progress.stop()
                        await self._interactive_prompt(test)
                        progress.start()

                    # Run the test with timeout
                    progress.update(overall, description=f"[cyan]{cat}[/] → {test.name}")
                    try:
                        result = await asyncio.wait_for(
                            test._run_with_timing(connection),
                            timeout=self.timeout,
                        )
                    except asyncio.TimeoutError:
                        result = test.error(f"Test timed out after {self.timeout}s")
                    except Exception as e:
                        result = test.error(str(e))

                    self.results.append(result)
                    self._print_result(result)
                    progress.advance(overall)

        # Print summary
        self._print_summary()
        return self.results

    async def _interactive_prompt(self, test: OCPPTest):
        """Prompt user for physical actions."""
        prompts = {
            "authorize_valid_idtag": "👆 Tap a VALID RFID card on the charger",
            "authorize_invalid_idtag": "👆 Tap an INVALID/UNKNOWN RFID card on the charger",
        }
        prompt_text = prompts.get(test.name, f"👆 Action needed for test: {test.name}")
        console.print()
        console.print(Panel(
            f"[bold yellow]{prompt_text}[/]\n\n"
            f"[dim]{test.description}[/]",
            title="⚡ Physical Action Required",
            border_style="yellow",
        ))
        console.input("[dim]Press Enter when ready...[/]")

    def _print_result(self, result: TestResult):
        """Print a single test result line."""
        status_styles = {
            TestStatus.PASS: "[bold green]✅ PASS[/]",
            TestStatus.FAIL: "[bold red]❌ FAIL[/]",
            TestStatus.SKIP: "[dim]⏭  SKIP[/]",
            TestStatus.ERROR: "[bold magenta]⚠  ERR [/]",
        }
        severity_styles = {
            Severity.CRITICAL: "[bold red]CRIT[/]",
            Severity.WARNING: "[yellow]WARN[/]",
            Severity.INFO: "[blue]INFO[/]",
        }
        status_str = status_styles.get(result.status, result.status.value)
        sev_str = severity_styles.get(result.severity, result.severity.value)

        msg = result.message[:80] if result.message else ""
        console.print(
            f"  {status_str} {sev_str} [dim]{result.test_name:<40}[/] {msg}"
        )

    def _print_summary(self):
        """Print final test summary."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if r.failed)
        skipped = sum(1 for r in self.results if r.skipped)
        errors = sum(1 for r in self.results if r.status == TestStatus.ERROR)

        effective = total - skipped
        pct = (passed / effective * 100) if effective > 0 else 100.0

        from report.generator import calculate_grade
        grade, grade_label = calculate_grade(pct)

        # Grade colors
        if pct >= 90:
            grade_style = "bold green"
        elif pct >= 65:
            grade_style = "bold yellow"
        else:
            grade_style = "bold red"

        console.print()
        console.print(Panel(
            f"[{grade_style}]Grade: {grade} — {grade_label}[/]\n\n"
            f"  [green]✅ Passed:  {passed}[/]\n"
            f"  [red]❌ Failed:  {failed}[/]\n"
            f"  [dim]⏭  Skipped: {skipped}[/]\n"
            f"  [magenta]⚠  Errors:  {errors}[/]\n"
            f"  ─────────────────\n"
            f"  Total:    {total}\n"
            f"  Pass rate: [{grade_style}]{pct:.1f}%[/]",
            title="📊 Test Summary",
            border_style="cyan",
        ))

        # List critical failures
        critical_fails = [r for r in self.results if r.failed and r.severity == Severity.CRITICAL]
        if critical_fails:
            console.print()
            console.print("[bold red]⚠ Critical Failures:[/]")
            for r in critical_fails:
                console.print(f"  [red]• {r.test_name}[/] — {r.message[:80]}")


async def handle_boot_sequence(server: OCPPServer, connection: ChargerConnection,
                                 config: dict) -> bool:
    """Handle the initial boot sequence (BootNotification + StatusNotifications).
    
    This runs before the test suite to capture the charger's boot behavior.
    Returns True if boot was successful.
    """
    version = connection.ocpp_version

    console.print("[cyan]Waiting for BootNotification...[/]")

    # Register auto-response handlers for boot sequence
    boot_payload_captured = {}
    status_payloads: dict[int, dict] = {}
    heartbeat_interval = config.get("timing", {}).get("heartbeat_interval", 30)

    async def handle_boot(conn, uid, action, payload):
        boot_payload_captured.update(payload)
        conn.boot_payload = payload
        # Extract charger info
        if version == "2.0.1":
            cs = payload.get("chargingStation", {})
            conn.vendor = cs.get("vendorName", "")
            conn.model = cs.get("model", "")
            conn.serial = cs.get("serialNumber", "")
            conn.firmware = cs.get("firmwareVersion", "")
        else:
            conn.vendor = payload.get("chargePointVendor", "")
            conn.model = payload.get("chargePointModel", "")
            conn.serial = payload.get("chargePointSerialNumber", "")
            conn.firmware = payload.get("firmwareVersion", "")

        console.print(f"  [green]✓[/] BootNotification: {conn.vendor} {conn.model} (fw: {conn.firmware})")
        if version == "2.0.1":
            return msg201.boot_notification_conf("Accepted", heartbeat_interval)
        return msg16.boot_notification_conf("Accepted", heartbeat_interval)

    async def handle_status(conn, uid, action, payload):
        connector_id = payload.get("connectorId", payload.get("connectorId", 0))
        status_payloads[connector_id] = payload
        conn.status_by_connector = status_payloads
        status = payload.get("status", payload.get("connectorStatus", "?"))
        console.print(f"  [green]✓[/] StatusNotification: connector {connector_id} → {status}")
        return msg16.status_notification_conf()

    async def handle_heartbeat(conn, uid, action, payload):
        if version == "2.0.1":
            return msg201.heartbeat_conf()
        return msg16.heartbeat_conf()

    async def handle_authorize(conn, uid, action, payload):
        # During boot phase, auto-accept authorization
        id_tag = payload.get("idTag", payload.get("idToken", {}).get("idToken", ""))
        console.print(f"  [green]✓[/] Authorize: {id_tag} → Accepted")
        if version == "2.0.1":
            return msg201.authorize_conf("Accepted")
        return msg16.authorize_conf("Accepted")

    async def handle_start_txn(conn, uid, action, payload):
        connector_id = payload.get("connectorId", 1)
        meter_start = payload.get("meterStart", 0)
        txn_id = 0
        conn.active_transaction_id = txn_id
        conn.active_connector_id = connector_id
        conn.meter_start = meter_start
        console.print(f"  [green]✓[/] StartTransaction: connector={connector_id} meterStart={meter_start}")
        return msg16.start_transaction_conf(txn_id, "Accepted")

    async def handle_stop_txn(conn, uid, action, payload):
        txn_id = payload.get("transactionId", 0)
        meter_stop = payload.get("meterStop", 0)
        reason = payload.get("reason", "Local")
        conn.active_transaction_id = None
        console.print(f"  [green]✓[/] StopTransaction: txn={txn_id} meterStop={meter_stop} reason={reason}")
        return msg16.stop_transaction_conf("Accepted")

    async def handle_meter_values(conn, uid, action, payload):
        return msg16.meter_values_conf()

    async def handle_tx_event(conn, uid, action, payload):
        event_type = payload.get("eventType", "?")
        console.print(f"  [green]✓[/] TransactionEvent: {event_type}")
        return msg201.transaction_event_conf()

    async def handle_data_transfer(conn, uid, action, payload):
        return {"status": "Accepted"}

    async def handle_fw_status(conn, uid, action, payload):
        status = payload.get("status", "?")
        console.print(f"  [dim]FirmwareStatus: {status}[/]")
        return {}

    async def handle_diag_status(conn, uid, action, payload):
        return {}

    # Register handlers
    server.register_handler("BootNotification", handle_boot)
    server.register_handler("StatusNotification", handle_status)
    server.register_handler("Heartbeat", handle_heartbeat)
    server.register_handler("Authorize", handle_authorize)
    server.register_handler("StartTransaction", handle_start_txn)
    server.register_handler("StopTransaction", handle_stop_txn)
    server.register_handler("MeterValues", handle_meter_values)
    server.register_handler("TransactionEvent", handle_tx_event)
    server.register_handler("DataTransfer", handle_data_transfer)
    server.register_handler("FirmwareStatusNotification", handle_fw_status)
    server.register_handler("DiagnosticsStatusNotification", handle_diag_status)

    # Wait for boot sequence to complete
    boot_timeout = config.get("timing", {}).get("boot_timeout", 60)
    deadline = time.monotonic() + boot_timeout

    while not boot_payload_captured and time.monotonic() < deadline:
        await asyncio.sleep(0.5)

    if not boot_payload_captured:
        console.print("[bold red]✗ No BootNotification received within timeout[/]")
        return False

    # Wait a bit for StatusNotifications
    await asyncio.sleep(3)

    expected_connectors = config.get("charger", {}).get("num_connectors", 1)
    console.print(f"  [dim]Captured {len(status_payloads)} StatusNotification(s)[/]")

    return True


async def run_getconfig_phase(connection: ChargerConnection, config: dict):
    """Run GetConfiguration (1.6) or GetVariables (2.0.1) to discover charger capabilities."""
    version = connection.ocpp_version

    console.print("[cyan]Fetching charger configuration...[/]")

    if version == "2.0.1":
        # For 2.0.1, we'd use GetVariables — simplified here
        console.print("  [dim]GetVariables (2.0.1) — skipping for now[/]")
        return

    resp = await connection.send_call_and_wait("GetConfiguration", {}, timeout=15.0)
    if resp and not resp.get("_is_error"):
        config_keys = resp.get("configurationKey", [])
        for item in config_keys:
            if isinstance(item, dict) and "key" in item:
                connection.known_config[item["key"]] = str(item.get("value", ""))
        console.print(f"  [green]✓[/] GetConfiguration: {len(config_keys)} keys retrieved")

        # Log interesting values
        for key in ["HeartbeatInterval", "MeterValueSampleInterval", "NumberOfConnectors",
                     "SupportedFeatureProfiles"]:
            val = connection.known_config.get(key)
            if val:
                console.print(f"    [dim]{key} = {val}[/]")
    else:
        console.print("  [yellow]⚠ GetConfiguration failed or timed out[/]")


def preregister_handlers(server: OCPPServer, config: dict):
    """Register all message handlers BEFORE charger connects.
    
    This ensures BootNotification (sent immediately on connect) is handled.
    Handlers check connection.ocpp_version at call time, not registration time.
    """
    heartbeat_interval = config.get("timing", {}).get("heartbeat_interval", 30)
    
    async def handle_boot(conn, uid, action, payload):
        conn.boot_payload = payload
        v = conn.ocpp_version
        if v == "2.0.1":
            cs = payload.get("chargingStation", {})
            conn.vendor = cs.get("vendorName", "")
            conn.model = cs.get("model", "")
            conn.serial = cs.get("serialNumber", "")
            conn.firmware = cs.get("firmwareVersion", "")
            return msg201.boot_notification_conf("Accepted", heartbeat_interval)
        else:
            conn.vendor = payload.get("chargePointVendor", "")
            conn.model = payload.get("chargePointModel", "")
            conn.serial = payload.get("chargePointSerialNumber", "")
            conn.firmware = payload.get("firmwareVersion", "")
            return msg16.boot_notification_conf("Accepted", heartbeat_interval)

    async def handle_status(conn, uid, action, payload):
        cid = payload.get("connectorId", 0)
        conn.status_by_connector[cid] = payload
        return msg16.status_notification_conf()

    async def handle_heartbeat(conn, uid, action, payload):
        if conn.ocpp_version == "2.0.1":
            return msg201.heartbeat_conf()
        return msg16.heartbeat_conf()

    async def handle_authorize(conn, uid, action, payload):
        if conn.ocpp_version == "2.0.1":
            return msg201.authorize_conf("Accepted")
        return msg16.authorize_conf("Accepted")

    async def handle_start_txn(conn, uid, action, payload):
        txn_id = 0
        conn.active_transaction_id = txn_id
        conn.active_connector_id = payload.get("connectorId", 1)
        conn.meter_start = payload.get("meterStart", 0)
        return msg16.start_transaction_conf(txn_id, "Accepted")

    async def handle_stop_txn(conn, uid, action, payload):
        conn.active_transaction_id = None
        return msg16.stop_transaction_conf("Accepted")

    async def handle_meter(conn, uid, action, payload):
        return msg16.meter_values_conf()

    async def handle_tx_event(conn, uid, action, payload):
        return msg201.transaction_event_conf()

    async def handle_data(conn, uid, action, payload):
        return {"status": "Accepted"}

    async def handle_fw(conn, uid, action, payload):
        return {}

    server.register_handler("BootNotification", handle_boot)
    server.register_handler("StatusNotification", handle_status)
    server.register_handler("Heartbeat", handle_heartbeat)
    server.register_handler("Authorize", handle_authorize)
    server.register_handler("StartTransaction", handle_start_txn)
    server.register_handler("StopTransaction", handle_stop_txn)
    server.register_handler("MeterValues", handle_meter)
    server.register_handler("TransactionEvent", handle_tx_event)
    server.register_handler("DataTransfer", handle_data)
    server.register_handler("FirmwareStatusNotification", handle_fw)
    server.register_handler("SecurityEventNotification", handle_fw)
