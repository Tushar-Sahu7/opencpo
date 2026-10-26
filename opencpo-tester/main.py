#!/usr/bin/env python3
"""
OCPP Compliance Tester

Acts as a CSMS server, waits for a charger to connect, runs the full OCPP
compliance test suite, and generates a professional deviation report.

Usage:
    ocpp-tester --port 9300 --version auto --report both
    ocpp-tester --port 9300 --tests boot,status --interactive
    ocpp-tester --port 9300 --full --report pdf --output charger-2026.pdf
"""
import argparse
import asyncio
import json
import logging
import os
import sys
from os import environ
from datetime import datetime, timezone
from pathlib import Path

import yaml
from rich.console import Console
from rich.panel import Panel

from server import OCPPServer
from runner import TestRunner, handle_boot_sequence, run_getconfig_phase, preregister_handlers
from report.generator import ReportGenerator
from report.html import generate_html
from report.pdf import generate_pdf
from tests.base import Severity

console = Console()


def load_config(config_path: str = None) -> dict:
    """Load configuration from YAML file, with defaults."""
    defaults = {
        "server": {"port": 9300, "version": "auto", "tls": False},
        "charger": {"num_connectors": 1},
        "timing": {
            "heartbeat_interval": 30,
            "meter_interval": 10,
            "boot_timeout": 60,
            "test_timeout": 120,
            "transaction_start_max": 5,
        },
        "tests": {"skip": [], "only": [], "full": False, "interactive": True},
        "branding": {
            "company": "OCPP Compliance Tester",
            "logo_path": None,
            "logo_color_path": None,
            "primary_color": "#1e3a5f",
            "accent_color": "#2563eb",
            "green_color": "#16a34a",
        },
        "report": {"format": "both", "output": None},
        "rfid": {"valid_tag": "", "invalid_tag": ""},
        "ai": {
            "enabled": False,
            "provider": "ollama",
            "api_url": "http://127.0.0.1:11434",
            "api_key": "",
            "model": "llama3.3:70b",
            "timeout": 120,
        },
    }

    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            file_config = yaml.safe_load(f) or {}
        # Deep merge
        for section, values in file_config.items():
            if section in defaults and isinstance(defaults[section], dict) and isinstance(values, dict):
                defaults[section].update(values)
            else:
                defaults[section] = values

    return defaults


def parse_args():
    parser = argparse.ArgumentParser(
        prog="ocpp-tester",
        description="OCPP Compliance Tester — automated OCPP 1.6/2.0.1 compliance testing for EV chargers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ocpp-tester                                    # Default: port 9300, auto-detect, interactive
  ocpp-tester --port 9300 --version 1.6          # Force OCPP 1.6
  ocpp-tester --tests boot,status,transactions   # Run specific categories only
  ocpp-tester --skip firmware,smart_charging     # Skip certain categories
  ocpp-tester --full --report pdf                # Full suite with PDF report
  ocpp-tester --no-interactive                   # Skip tests requiring physical actions
        """
    )
    parser.add_argument("--port", type=int, default=int(environ.get("PORT", "9300")),
                        help="WebSocket server port (default: 9300, or $PORT env var)")
    parser.add_argument("--host", default="0.0.0.0",
                        help="WebSocket server bind address (default: 0.0.0.0)")
    parser.add_argument("--version", choices=["1.6", "2.0.1", "auto"], default="auto",
                        help="OCPP version (default: auto-detect from subprotocol)")
    parser.add_argument("--tests", type=str, default=None,
                        help="Comma-separated test categories to run")
    parser.add_argument("--skip", type=str, default=None,
                        help="Comma-separated test categories to skip")
    parser.add_argument("--full", action="store_true",
                        help="Run all tests including firmware/diagnostics")
    parser.add_argument("--report", choices=["pdf", "html", "both", "none"], default="both",
                        help="Report format (default: both)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output file path (default: auto-generated)")
    parser.add_argument("--timeout", type=int, default=120,
                        help="Per-test timeout in seconds (default: 120)")
    parser.add_argument("--interactive", action="store_true", default=True,
                        help="Enable interactive prompts for physical tests (default)")
    parser.add_argument("--no-interactive", action="store_true",
                        help="Disable interactive prompts")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to config.yaml (default: ./config.yaml)")
    parser.add_argument("--tls-cert", type=str, default=None,
                        help="TLS certificate file for WSS")
    parser.add_argument("--tls-key", type=str, default=None,
                        help="TLS private key file for WSS")
    parser.add_argument("--company", type=str, default=None,
                        help="Company name for reports (default: from config or 'OCPP Compliance Tester')")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Verbose logging")

    # ── AI / profile generation ───────────────────────────────────────────────
    ai_group = parser.add_argument_group("AI Profile Generation")
    ai_group.add_argument("--generate-profile", action="store_true",
                          help="After tests complete, use AI to generate a ChargerProfile dataclass")
    ai_group.add_argument("--no-ai", action="store_true",
                          help="Disable AI features even if configured in config.yaml")
    ai_group.add_argument("--ai-url", type=str, default=None, metavar="URL",
                          help="AI inference endpoint (overrides config ai.api_url)")
    ai_group.add_argument("--ai-key", type=str, default=None, metavar="KEY",
                          help="API key for inference endpoint (overrides config ai.api_key)")
    ai_group.add_argument("--ai-model", type=str, default=None, metavar="MODEL",
                          help="AI model name to use (overrides config ai.model)")

    return parser.parse_args()


async def _run_ai_profile_generation(
    report_json: dict,
    report_data,
    connection,
    config: dict,
    json_path: str,
    base_name: str,
    console: Console,
) -> None:
    """Generate a ChargerProfile using AI and write it to disk."""
    try:
        from profile_generator import generate_profile
    except ImportError as e:
        console.print(f"  [yellow]⚠[/] AI profile generation unavailable: {e}")
        return

    ai_config = config.get("ai", {})
    model = ai_config.get("model", "llama3.3:70b")
    api_url = ai_config.get("api_url", "http://127.0.0.1:11434")

    console.print()
    console.print(f"[cyan]Generating ChargerProfile with AI[/] "
                  f"[dim](model: {model} @ {api_url})[/]")
    console.print("[dim]  This may take 30-120 seconds...[/]")

    profile_code = await generate_profile(report_json, connection, config)

    if not profile_code:
        console.print("  [yellow]⚠[/] AI profile generation returned no result — check logs")
        return

    # Write profile file
    charger = report_json.get("charger", {})
    vendor = (charger.get("vendor") or "unknown").replace(" ", "_")
    model_name = (charger.get("model") or "charger").replace(" ", "_")
    profile_filename = f"{base_name}_profile.py"
    Path(profile_filename).write_text(profile_code)
    console.print(f"  [green]✓[/] ChargerProfile: [bold]{profile_filename}[/]")

    # Also embed in JSON output
    try:
        existing_json = json.loads(Path(json_path).read_text())
        existing_json["generated_profile"] = profile_code
        Path(json_path).write_text(json.dumps(existing_json, indent=2))
        console.print(f"  [green]✓[/] Profile embedded in JSON output")
    except Exception as e:
        console.print(f"  [yellow]⚠[/] Could not embed profile in JSON: {e}")

    # Print the profile with syntax highlighting if rich is available
    try:
        from rich.syntax import Syntax
        from rich.panel import Panel as RichPanel
        syntax = Syntax(profile_code, "python", theme="monokai", line_numbers=False)
        console.print()
        console.print(RichPanel(
            syntax,
            title=f"[bold green]Generated ChargerProfile — {vendor} {model_name}[/]",
            border_style="green",
            padding=(0, 1),
        ))
    except Exception:
        # Fallback: just print it
        console.print()
        console.print("[bold green]Generated ChargerProfile:[/]")
        console.print(profile_code)


async def main():
    args = parse_args()

    # Logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quiet down websockets library
    logging.getLogger("websockets").setLevel(logging.WARNING)

    # Load config
    config_path = args.config
    if not config_path:
        # Try current directory, then script directory
        for p in ["config.yaml", Path(__file__).parent / "config.yaml"]:
            if Path(p).exists():
                config_path = str(p)
                break

    config = load_config(config_path)

    # Apply CLI overrides
    config["server"]["port"] = args.port
    config["timing"]["test_timeout"] = args.timeout
    if args.no_interactive:
        config["tests"]["interactive"] = False
    if args.company:
        if "branding" not in config:
            config["branding"] = {}
        config["branding"]["company"] = args.company
    if args.tls_cert:
        config["server"]["tls"] = True
        config["server"]["tls_cert"] = args.tls_cert
        config["server"]["tls_key"] = args.tls_key

    # AI config overrides
    if args.no_ai:
        config["ai"]["enabled"] = False
    if args.generate_profile:
        config["ai"]["enabled"] = True  # --generate-profile implies AI on
    if args.ai_url:
        config["ai"]["api_url"] = args.ai_url
    if args.ai_key:
        config["ai"]["api_key"] = args.ai_key
    if args.ai_model:
        config["ai"]["model"] = args.ai_model

    # Flatten config for easy access by tests
    flat_config = {}
    for section, values in config.items():
        if isinstance(values, dict):
            flat_config.update(values)
        else:
            flat_config[section] = values

    # Parse test categories
    categories = None
    if args.tests:
        categories = [t.strip() for t in args.tests.split(",")]
    skip = None
    if args.skip:
        skip = [t.strip() for t in args.skip.split(",")]

    # Banner
    company_name = config.get("branding", {}).get("company", "OCPP Compliance Tester")
    console.print()
    console.print(Panel(
        f"[bold blue]⚡ OCPP Compliance Tester[/] [dim]— {company_name}[/]\n"
        f"[dim]Port: {args.port} | Version: {args.version} | Interactive: {not args.no_interactive}[/]",
        border_style="blue",
    ))

    # Start server
    server = OCPPServer(
        host=args.host,
        port=args.port,
        tls_cert=config["server"].get("tls_cert"),
        tls_key=config["server"].get("tls_key"),
    )

    async with server:
        protocol = "wss" if config["server"].get("tls") else "ws"
        console.print(f"[cyan]Listening on {protocol}://{args.host}:{args.port}/ocpp/{{charger_id}}[/]")
        console.print("[yellow]Point your charger at this address and wait for connection...[/]")
        console.print()

        # Pre-register handlers BEFORE charger connects
        # (charger sends BootNotification immediately on connection)
        preregister_handlers(server, config)

        # Wait for charger to connect
        boot_timeout = config["timing"]["boot_timeout"]
        connection = await server.wait_for_connection(timeout=boot_timeout)

        if not connection:
            console.print(f"[bold red]No charger connected within {boot_timeout}s — aborting.[/]")
            return 1

        console.print(f"[green]✓ Charger connected:[/] {connection.charger_id} "
                       f"(OCPP {connection.ocpp_version})")
        console.print()

        # Wait for BootNotification (already handled by preregister_handlers)
        console.print("[cyan]Waiting for BootNotification...[/]")
        import time as _time

        # First: wait 10s for spontaneous BootNotification
        deadline = _time.monotonic() + 10
        while not connection.boot_payload and _time.monotonic() < deadline:
            await asyncio.sleep(0.5)

        if not connection.boot_payload:
            # No spontaneous boot — charger thinks it's already booted
            # Try TriggerMessage to force a BootNotification
            console.print("[yellow]  ⏳ No spontaneous BootNotification — sending TriggerMessage...[/]")
            try:
                trigger_payload = {"requestedMessage": "BootNotification"}
                uid, fut = await connection.send_call("TriggerMessage", trigger_payload)
                try:
                    resp = await asyncio.wait_for(fut, timeout=5)
                    console.print(f"  [dim]TriggerMessage response: {resp}[/]")
                except asyncio.TimeoutError:
                    console.print("[dim]  TriggerMessage: no response (charger may not support it)[/]")
            except Exception as e:
                console.print(f"[dim]  TriggerMessage failed: {e}[/]")

            # Wait another 15s for the triggered BootNotification
            deadline = _time.monotonic() + 15
            while not connection.boot_payload and _time.monotonic() < deadline:
                await asyncio.sleep(0.5)

        if not connection.boot_payload:
            # Still no boot — use GetConfiguration to populate charger info
            console.print("[yellow]  ⚠ No BootNotification received — using GetConfiguration fallback[/]")
            try:
                uid, fut = await connection.send_call("GetConfiguration", {"key": []})
                resp = await asyncio.wait_for(fut, timeout=10)
                config_list = resp.get("configurationKey", [])
                config_map = {c["key"]: c.get("value", "") for c in config_list if isinstance(c, dict)}
                connection.vendor = config_map.get("ChargePointVendor", "Unknown")
                connection.model = config_map.get("ChargePointModel", "Unknown")
                connection.serial = config_map.get("ChargePointSerialNumber", "Unknown")
                connection.firmware = config_map.get("FirmwareVersion", "Unknown")
                connection.known_config = config_map
                console.print(f"  [green]✓[/] GetConfiguration: {connection.vendor} {connection.model} (fw: {connection.firmware})")
                console.print(f"  [dim]({len(config_map)} configuration keys retrieved)[/]")
            except Exception as e:
                console.print(f"[bold red]✗ GetConfiguration also failed: {e}[/]")
                console.print("[bold red]Cannot identify charger — aborting.[/]")
                return 1
        else:
            console.print(f"  [green]✓[/] BootNotification: {connection.vendor} {connection.model} (fw: {connection.firmware})")

        # Wait a few seconds for StatusNotifications
        await asyncio.sleep(3)
        for cid, sp in connection.status_by_connector.items():
            status = sp.get("status", sp.get("connectorStatus", "?"))
            console.print(f"  [green]✓[/] StatusNotification: connector {cid} → {status}")

        # Fetch charger configuration (GetConfiguration)
        await run_getconfig_phase(connection, config)
        console.print()

        # Clear handlers — tests will manage their own responses
        # Keep essential handlers registered for background operation
        # (tests that need specific handling will override)

        # Run tests
        runner = TestRunner(flat_config)
        results = await runner.run_all(
            server=server,
            connection=connection,
            categories=categories,
            skip=skip,
            full=args.full,
        )

        # Generate report
        if args.report != "none":
            console.print()
            console.print("[cyan]Generating reports...[/]")

            generator = ReportGenerator(config)
            report_data = generator.build(
                results=results,
                connection=connection,
                message_log=server.log.get_all(),
            )

            # Generate output path
            date_str = datetime.now().strftime("%Y-%m-%d")
            vendor = connection.vendor or "unknown"
            model = connection.model or "charger"
            base_name = args.output or f"report-{vendor}-{model}-{date_str}"
            base_name = base_name.replace(" ", "_")

            if args.report in ("html", "both"):
                html_path = base_name if base_name.endswith(".html") else f"{base_name}.html"
                generate_html(report_data, html_path)
                console.print(f"  [green]✓[/] HTML report: [bold]{html_path}[/]")

            if args.report in ("pdf", "both"):
                pdf_path = base_name if base_name.endswith(".pdf") else f"{base_name}.pdf"
                if generate_pdf(report_data, pdf_path):
                    console.print(f"  [green]✓[/] PDF report:  [bold]{pdf_path}[/]")
                else:
                    console.print(f"  [yellow]⚠[/] PDF generation failed (install reportlab)")

            # Always write JSON alongside other reports (for ops dashboard consumption)
            json_base = base_name.removesuffix(".pdf")
            json_path = f"{json_base}.json"
            report_json = report_data.to_json()
            Path(json_path).write_text(json.dumps(report_json, indent=2))
            console.print(f"  [green]✓[/] JSON results: [bold]{json_path}[/]")

            # ── AI profile generation ──────────────────────────────────────────
            if config.get("ai", {}).get("enabled", False):
                await _run_ai_profile_generation(
                    report_json=report_json,
                    report_data=report_data,
                    connection=connection,
                    config=config,
                    json_path=json_path,
                    base_name=json_base,
                    console=console,
                )

        # Exit code based on results
        critical_fails = sum(1 for r in results
                             if r.failed and r.severity == Severity.CRITICAL)
        if critical_fails > 0:
            console.print(f"\n[bold red]⚠ {critical_fails} critical failure(s) — charger is NOT compliant[/]")
            return 2

        any_fails = sum(1 for r in results if r.failed)
        if any_fails > 0:
            console.print(f"\n[yellow]⚠ {any_fails} failure(s) found — see report for details[/]")
            return 1

        console.print(f"\n[bold green]✅ All tests passed — charger is OCPP compliant[/]")
        return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code or 0)
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted — exiting.[/]")
        sys.exit(130)
