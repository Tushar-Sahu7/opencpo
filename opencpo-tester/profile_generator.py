"""
AI-powered ChargerProfile generator for OpenCPO compliance tester.

Takes compliance test results and charger telemetry, sends them to an LLM
(Ollama or OpenAI-compatible), and gets back a ready-to-use ChargerProfile
Python dataclass.

Usage:
    from profile_generator import generate_profile
    code = await generate_profile(report_data, connection, config)
"""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


# ── Embedded ChargerProfile schema ────────────────────────────────────────────
# Keep in sync with opencpo-core/charger_profiles/registry.py

CHARGERPROFILE_SCHEMA = '''\
@dataclass(frozen=True)
class ChargerProfile:
    """Describes charger-specific behavior for the OCPP handler."""

    # Identity
    id: str                          # e.g. "vendor-model-fw"
    vendor: str                      # e.g. "MYVENDOR"
    model_pattern: str               # regex, e.g. "CCS2.*"
    firmware_pattern: str = ".*"     # regex, e.g. "V3\\\\..*"
    description: str = ""

    # ── MeterValues behavior ─────────────────────────────────────────────
    sends_power_measurand: bool = True          # sends Power.Active.Import?
    power_unit: str = "W"                       # W or kW
    energy_unit: str = "Wh"                     # Wh or kWh
    meter_interval_sec: int = 10                # expected sample interval
    has_dual_voltage_current: bool = False       # sends two V/I pairs per sample?
    soc_available: bool = True                   # sends SoC?

    # ── Session behavior ─────────────────────────────────────────────────
    authorize_after_remote_start: bool = False   # sends Authorize AFTER accepting RemoteStart?
    remote_start_latency_ms: int = 200           # typical RemoteStart response time
    preparing_on_boot: bool = False              # connectors show Preparing after boot (not Available)?
    reports_connector_zero: bool = False          # sends StatusNotification for connector 0?
    resumes_session_after_reboot: bool = False    # keeps session alive across reboots?
    resumes_session_after_reconnect: bool = True  # continues session on WS reconnect (no reboot)?

    # ── Boot/reconnect behavior ──────────────────────────────────────────
    boot_time_sec: int = 20                      # time from power-on to BootNotification
    reconnect_retry_sec: int = 10                # WS reconnect interval
    sends_boot_on_reconnect: bool = False         # sends BootNotification on WS reconnect?
    stop_reason_on_reboot: str = "Other"          # StopTransaction reason when rebooting mid-session
    sends_status_on_boot: bool = True             # sends StatusNotification for all connectors after boot?

    # ── Power characteristics ────────────────────────────────────────────
    max_power_kw: float = 60.0                   # rated max power
    ramp_time_sec: int = 30                      # 0 to max power ramp time
    power_tapers_above_soc: int = 80             # SoC% where power starts tapering

    # ── Protocol compliance (from compliance testing) ────────────────────
    smart_charging_safe: bool = True              # can receive SetChargingProfile without disconnecting?
    unknown_action_returns_error: bool = True     # responds CALL_ERROR to unknown actions (spec-compliant)?
    heartbeat_drift_pct: float = 10.0             # acceptable heartbeat interval drift %

    # ── Quirks (free-form, for documentation) ────────────────────────────
    quirks: list[str] = field(default_factory=list)
'''

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are an OCPP charger compatibility expert. Given compliance test results and charger telemetry, generate an accurate ChargerProfile dataclass for the OpenCPO platform.

Rules:
- Every field value must be justified by a specific test result or observation
- If a test was skipped or inconclusive, use the conservative/safe default
- Include ALL observed quirks in the quirks list
- Reference OCPP spec sections where relevant (e.g. §4, §5.2)
- The profile must be valid Python that can be directly imported
- Use the exact ChargerProfile dataclass schema provided
- Each field assignment should have an inline comment explaining WHY that value was chosen
- The output must be ONLY the Python code block — no explanations before or after
- Start with the necessary imports, then the ChargerProfile instantiation
- Use a variable name like VENDOR_MODEL = ChargerProfile(...)
"""

# ── Example profile (embedded for prompt context) ────────────────────────────

_EXAMPLE_PROFILE = '''\
from dataclasses import field
from charger_profiles.registry import ChargerProfile

MAXPOWER_CCS2_V3 = ChargerProfile(
    id="maxpower-ccs2-v3",
    vendor="MAXPOWER",
    model_pattern=r"CCS2.*",
    firmware_pattern=r"DC2_D_V3\\..*",
    description="Maxpower 60kW DC CCS2 dual-gun, firmware V3.x",

    # MeterValues — confirmed by meter_values/power_unit test
    sends_power_measurand=True,          # ✓ PASS: Power.Active.Import observed in MeterValues
    power_unit="W",                      # Observed values like 55826 — clearly Watts, not kW
    energy_unit="Wh",                    # meterStart in Wh, confirmed by transactions test
    meter_interval_sec=10,               # MeterValueSampleInterval GetConfiguration = "10"
    has_dual_voltage_current=True,        # Observed: 2x Voltage + 2x Current per sample
    soc_available=True,                  # SoC measurand present in MeterValues samples

    # Session behavior
    authorize_after_remote_start=True,   # ✗ FAIL auth/authorize_order: Authorize AFTER RemoteStart acceptance
    remote_start_latency_ms=200,         # Observed from timing in remote_control tests
    preparing_on_boot=True,              # status/boot_status: connectors show Preparing, not Available
    reports_connector_zero=True,          # status/connector_zero: StatusNotification for connector 0 observed
    resumes_session_after_reboot=False,   # transactions/resume_after_reboot: FAIL — session lost on reboot
    resumes_session_after_reconnect=True, # Observed: session continues on WS reconnect without reboot

    # Boot/reconnect
    boot_time_sec=20,                    # Measured: 20s from power-on to BootNotification
    reconnect_retry_sec=10,              # Observed WS reconnect interval ~10s
    sends_boot_on_reconnect=False,        # ✓ PASS: only Heartbeat on reconnect, not BootNotification
    stop_reason_on_reboot="Other",       # StopTransaction reason observed on reboot
    sends_status_on_boot=False,           # ✗ FAIL boot/status_on_boot: intermittent — sometimes none

    # Power
    max_power_kw=60.0,                   # Rated 60kW, max observed 57.8kW
    ramp_time_sec=30,                    # Observed ~30s 0→max ramp
    power_tapers_above_soc=80,           # Typical DC charging taper point

    # Protocol compliance
    smart_charging_safe=False,            # ✗ FAIL smart_charging/ws_stability: drops WS on SetChargingProfile
    unknown_action_returns_error=False,   # ✗ FAIL protocol/unknown_action: returns CALL_RESULT (should be CALL_ERROR §4)
    heartbeat_drift_pct=15.0,            # Measured: up to ~15% drift from configured interval

    quirks=[
        "Dual V/I in MeterValues: first pair = DC connector output, second = DC bus/input",
        "Power.Active.Import sent in W (not kW) — values like 55826",
        "PROTOCOL: returns CALL_RESULT for unknown actions (should be CALL_ERROR per OCPP 1.6 §4)",
        "PROTOCOL: drops WebSocket on SmartCharging commands (SetChargingProfile, ClearChargingProfile, GetCompositeSchedule §5.8)",
        "PROTOCOL: intermittent StatusNotification on boot — sometimes sends for all connectors, sometimes none",
        "SESSION: Authorize sent AFTER accepting RemoteStart (reversed from OCPP 1.6 §5.11 expectation)",
    ],
)'''


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_prompt(report_data: dict, connection, config: dict) -> str:
    """Build the LLM prompt from test results and charger data."""

    # Charger identity
    charger = report_data.get("charger", {})
    vendor = charger.get("vendor", "Unknown")
    model_name = charger.get("model", "Unknown")
    serial = charger.get("serial", "Unknown")
    firmware = charger.get("firmware", "Unknown")
    ocpp_version = charger.get("ocpp_version", "1.6")

    # GetConfiguration data
    known_config: dict = {}
    if connection and hasattr(connection, "known_config"):
        known_config = connection.known_config or {}

    # Test results
    results = report_data.get("results", [])

    # Status notifications observed
    status_by_connector: dict = {}
    if connection and hasattr(connection, "status_by_connector"):
        status_by_connector = connection.status_by_connector or {}

    # Analyze message log for action patterns
    message_log = report_data.get("message_log", [])
    actions_seen: dict[str, int] = {}
    for entry in message_log:
        parsed = entry.get("parsed")
        if isinstance(parsed, list) and len(parsed) >= 3 and parsed[0] == 2:
            action = parsed[2]
            actions_seen[action] = actions_seen.get(action, 0) + 1

    # Meter value analysis
    meter_analysis = _analyze_meter_values(message_log)

    parts: list[str] = []

    # ── Identity ──────────────────────────────────────────────────────────────
    parts.append("## CHARGER IDENTITY")
    parts.append(f"- Vendor: {vendor}")
    parts.append(f"- Model: {model_name}")
    parts.append(f"- Serial: {serial}")
    parts.append(f"- Firmware: {firmware}")
    parts.append(f"- OCPP Version: {ocpp_version}")
    parts.append("")

    # ── GetConfiguration ──────────────────────────────────────────────────────
    if known_config:
        parts.append("## GETCONFIGURATION RESULTS")
        for key in sorted(known_config):
            parts.append(f"- {key}: {known_config[key]!r}")
        parts.append("")

    # ── Test results ──────────────────────────────────────────────────────────
    parts.append("## COMPLIANCE TEST RESULTS")
    for r in results:
        status = r.get("status", "UNKNOWN")
        name = r.get("name", "?")
        category = r.get("category", "?")
        severity = r.get("severity", "INFO")
        message = r.get("message", "")
        spec_ref = r.get("spec_ref", "")
        fix_rec = r.get("fix_recommendation", "")

        icon = {"PASS": "✓", "FAIL": "✗", "SKIP": "⊘", "ERROR": "!"}.get(status, "?")
        line = f"[{icon} {status}] [{severity}] {category}/{name}"
        if message:
            line += f": {message}"
        if spec_ref:
            line += f" (Spec: {spec_ref})"
        if fix_rec and status not in ("PASS", "SKIP"):
            line += f" → Fix: {fix_rec}"
        parts.append(line)
    parts.append("")

    # ── Status notifications ──────────────────────────────────────────────────
    if status_by_connector:
        parts.append("## STATUS NOTIFICATIONS OBSERVED")
        for cid in sorted(status_by_connector):
            sp = status_by_connector[cid]
            status = sp.get("status", sp.get("connectorStatus", "?"))
            error_code = sp.get("errorCode", "")
            suffix = f" (errorCode: {error_code})" if error_code and error_code != "NoError" else ""
            parts.append(f"- Connector {cid}: {status}{suffix}")
        parts.append("")

    # ── Message patterns ──────────────────────────────────────────────────────
    if actions_seen:
        parts.append("## MESSAGES RECEIVED FROM CHARGER (action → count)")
        for action in sorted(actions_seen):
            parts.append(f"- {action}: {actions_seen[action]}")
        parts.append("")

    # ── MeterValues analysis ──────────────────────────────────────────────────
    if meter_analysis:
        parts.append("## METERVALUES ANALYSIS")
        for line in meter_analysis:
            parts.append(f"- {line}")
        parts.append("")

    # ── Failures ──────────────────────────────────────────────────────────────
    failures = [r for r in results if r.get("status") in ("FAIL", "ERROR")]
    if failures:
        parts.append("## FAILURES & DEVIATIONS (key input for quirks list)")
        for r in failures:
            sev = r.get("severity", "INFO")
            name = r.get("name", "?")
            cat = r.get("category", "?")
            msg = r.get("message", "")
            spec = r.get("spec_ref", "")
            line = f"- [{sev}] {cat}/{name}: {msg}"
            if spec:
                line += f" (Spec: {spec})"
            parts.append(line)
        parts.append("")

    # ── Schema ────────────────────────────────────────────────────────────────
    parts.append("## CHARGERPROFILE SCHEMA (use this exact definition)")
    parts.append("```python")
    parts.append(CHARGERPROFILE_SCHEMA)
    parts.append("```")
    parts.append("")

    # ── Example ───────────────────────────────────────────────────────────────
    parts.append("## REFERENCE EXAMPLE (match this style exactly)")
    parts.append("```python")
    parts.append(_EXAMPLE_PROFILE)
    parts.append("```")
    parts.append("")

    # ── Task ──────────────────────────────────────────────────────────────────
    var_name = _make_var_name(vendor, model_name)
    profile_id = _make_profile_id(vendor, model_name, firmware)
    parts.append("## YOUR TASK")
    parts.append(f"Generate a complete ChargerProfile for {vendor} {model_name} (firmware: {firmware}).")
    parts.append(f"Use variable name: {var_name}")
    parts.append(f"Use profile id: {profile_id!r}")
    parts.append("")
    parts.append("Output ONLY the Python code block. No prose before or after.")
    parts.append("Every field should have an inline comment citing which test/observation justifies it.")
    parts.append("The quirks list must include ALL deviations found, with spec section references.")

    return "\n".join(parts)


def _analyze_meter_values(message_log: list) -> list[str]:
    """Analyze MeterValues messages from the log and summarize findings."""
    findings: list[str] = []
    measurands_seen: set[str] = set()
    units_seen: dict[str, str] = {}
    energy_values: list[float] = []
    power_values: list[float] = []
    soc_values: list[float] = []
    voltage_count_per_sample: list[int] = []
    current_count_per_sample: list[int] = []

    for entry in message_log:
        parsed = entry.get("parsed")
        if not isinstance(parsed, list) or len(parsed) < 4 or parsed[0] != 2:
            continue
        if parsed[2] != "MeterValues":
            continue

        payload = parsed[3] if len(parsed) > 3 else {}
        meter_value_list = payload.get("meterValue", [])

        for mv in meter_value_list:
            sampled = mv.get("sampledValue", [])
            v_count = 0
            i_count = 0
            for sv in sampled:
                measurand = sv.get("measurand", "Energy.Active.Import.Register")
                unit = sv.get("unit", "Wh")
                value_str = sv.get("value", "")

                measurands_seen.add(measurand)
                units_seen[measurand] = unit

                try:
                    value = float(value_str)
                    if measurand == "Energy.Active.Import.Register":
                        energy_values.append(value)
                    elif measurand == "Power.Active.Import":
                        power_values.append(value)
                    elif measurand == "SoC":
                        soc_values.append(value)
                    elif measurand == "Voltage":
                        v_count += 1
                    elif measurand == "Current.Import":
                        i_count += 1
                except (ValueError, TypeError):
                    pass

            if v_count > 0:
                voltage_count_per_sample.append(v_count)
            if i_count > 0:
                current_count_per_sample.append(i_count)

    if not measurands_seen:
        return findings

    findings.append(f"Measurands observed: {', '.join(sorted(measurands_seen))}")

    for measurand in sorted(units_seen):
        findings.append(f"Unit for {measurand}: {units_seen[measurand]}")

    if energy_values:
        unit = units_seen.get("Energy.Active.Import.Register", "Wh")
        findings.append(f"Energy range: {min(energy_values):.1f} – {max(energy_values):.1f} {unit}")

    if power_values:
        max_p = max(power_values)
        unit = units_seen.get("Power.Active.Import", "W")
        findings.append(f"Max power observed: {max_p:.0f} {unit}")
        if unit == "W" and max_p > 1000:
            findings.append(f"  → Power is in Watts (not kW): {max_p:.0f}W = {max_p/1000:.1f}kW")
        elif unit == "kW":
            findings.append(f"  → Power is in kW")

    if soc_values:
        findings.append(f"SoC range observed: {min(soc_values):.0f}% – {max(soc_values):.0f}%")

    if voltage_count_per_sample:
        max_v = max(voltage_count_per_sample)
        if max_v > 1:
            findings.append(f"Dual voltage readings: up to {max_v} Voltage values per sample (dual-gun?)")

    if current_count_per_sample:
        max_i = max(current_count_per_sample)
        if max_i > 1:
            findings.append(f"Dual current readings: up to {max_i} Current values per sample (dual-gun?)")

    return findings


# ── API call helpers ──────────────────────────────────────────────────────────

def _detect_api_format(api_url: str) -> str:
    """Detect whether to use Ollama or OpenAI-compatible API format."""
    url = api_url.rstrip("/")
    if "/v1" in url:
        return "openai"
    return "ollama"


async def _call_ollama(api_url: str, model: str, prompt: str, timeout: int) -> str:
    """Call Ollama /api/generate and return the response text."""
    import httpx

    url = api_url.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,    # Low temp for deterministic code generation
            "num_ctx": 8192,
        },
    }

    logger.info(f"Calling Ollama API: POST {url} (model={model})")
    async with httpx.AsyncClient(timeout=float(timeout)) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "")


async def _call_openai_compat(
    api_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: int,
) -> str:
    """Call OpenAI-compatible /chat/completions and return the response text."""
    import httpx

    url = api_url.rstrip("/") + "/chat/completions"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
    }

    logger.info(f"Calling OpenAI-compatible API: POST {url} (model={model})")
    async with httpx.AsyncClient(timeout=float(timeout)) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


# ── Code extraction ───────────────────────────────────────────────────────────

def _extract_code_block(text: str) -> str:
    """Extract Python code from LLM response (handles ```python blocks or raw code)."""
    # Try ```python ... ``` first
    pattern = r"```(?:python)?\s*\n(.*?)\n```"
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        # Return the longest match (most complete code block)
        return max(matches, key=len).strip()

    # Fallback: if no fences, try to find ChargerProfile( in raw text
    if "ChargerProfile(" in text:
        lines = text.split("\n")
        # Find first import or ChargerProfile line
        start_idx = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if (stripped.startswith("from ")
                    or stripped.startswith("import ")
                    or "ChargerProfile(" in stripped):
                start_idx = i
                break
        return "\n".join(lines[start_idx:]).strip()

    return text.strip()


# ── Name helpers ──────────────────────────────────────────────────────────────

def _make_var_name(vendor: str, model: str) -> str:
    """Convert vendor/model to a Python UPPER_SNAKE_CASE variable name."""
    raw = f"{vendor}_{model}"
    clean = re.sub(r"[^A-Za-z0-9]", "_", raw).upper()
    clean = re.sub(r"_+", "_", clean).strip("_")
    return clean or "CHARGER_PROFILE"


def _make_profile_id(vendor: str, model: str, firmware: str) -> str:
    """Generate a kebab-case profile ID string."""
    parts = [vendor, model]
    # Add first firmware segment if useful
    if firmware and firmware not in ("Unknown", "N/A", ""):
        fw_first = re.split(r"[._\-]", firmware)[0]
        if fw_first:
            parts.append(fw_first)
    clean_parts = [re.sub(r"[^a-z0-9]", "-", p.lower()) for p in parts]
    result = "-".join(p.strip("-") for p in clean_parts if p.strip("-"))
    result = re.sub(r"-+", "-", result).strip("-")
    return result or "custom-charger"


# ── Main entry point ──────────────────────────────────────────────────────────

async def generate_profile(
    report_data: dict,
    connection,
    config: dict,
) -> Optional[str]:
    """
    Generate a ChargerProfile Python code block using an LLM.

    Args:
        report_data:  dict from ReportData.to_json() — full test results
        connection:   ChargerConnection object (for known_config, status_by_connector, etc.)
        config:       Full config dict (reads config["ai"] section)

    Returns:
        Python code string ready to paste into a profiles file, or None on failure.
    """
    ai_config = config.get("ai", {})

    if not ai_config.get("enabled", False):
        logger.debug("AI profile generation disabled in config (ai.enabled is false)")
        return None

    api_url: str = ai_config.get("api_url", "http://127.0.0.1:11434")
    api_key: str = ai_config.get("api_key", "")
    model: str = ai_config.get("model", "llama3.3:70b")
    timeout: int = int(ai_config.get("timeout", 120))

    charger = report_data.get("charger", {})
    vendor = charger.get("vendor", "Unknown")
    model_name = charger.get("model", "Unknown")
    firmware = charger.get("firmware", "Unknown")

    logger.info(f"AI profile generation: {vendor} {model_name} via {model} at {api_url}")

    try:
        user_prompt = _build_prompt(report_data, connection, config)
        api_format = _detect_api_format(api_url)

        if api_format == "openai":
            raw_response = await _call_openai_compat(
                api_url, api_key, model,
                SYSTEM_PROMPT, user_prompt, timeout,
            )
        else:
            # Ollama: inject system prompt into the user prompt
            full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"
            raw_response = await _call_ollama(api_url, model, full_prompt, timeout)

        profile_code = _extract_code_block(raw_response)

        if not profile_code or "ChargerProfile(" not in profile_code:
            logger.warning(
                "LLM response did not contain a valid ChargerProfile.\n"
                f"First 500 chars of response:\n{raw_response[:500]}"
            )
            return None

        # Ensure required imports are present
        if "from charger_profiles.registry import" not in profile_code:
            profile_code = "from charger_profiles.registry import ChargerProfile\n" + profile_code
        if "field(" in profile_code and "from dataclasses import" not in profile_code:
            profile_code = "from dataclasses import field\n" + profile_code

        # Add a header comment
        date_str = report_data.get("generated_at", "")[:10] or "unknown date"
        profile_id = _make_profile_id(vendor, model_name, firmware)
        header = (
            f"# Generated ChargerProfile — {vendor} {model_name}\n"
            f"# Firmware: {firmware}\n"
            f"# OCPP: {charger.get('ocpp_version', '1.6')}\n"
            f"# Generated by OpenCPO compliance tester on {date_str}\n"
            f"# Profile ID: {profile_id}\n"
            f"#\n"
            f"# Auto-generated from compliance test results.\n"
            f"# Review and validate before using in production.\n"
            f"\n"
        )
        return header + profile_code

    except ImportError:
        logger.error(
            "httpx is required for AI profile generation. "
            "Install it with: pip install httpx"
        )
        return None
    except Exception as e:
        logger.error(f"Profile generation failed: {e}", exc_info=True)
        return None
