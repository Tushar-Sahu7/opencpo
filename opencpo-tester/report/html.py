"""
HTML Report Generator — Standalone HTML for email/browser.
Branding (colors, logo, company name) is read from report.branding, not hardcoded.
"""
import base64
import json
import html
from datetime import datetime
from pathlib import Path

from tests.base import TestStatus, Severity
from report.generator import ReportData, CategorySummary


SEVERITY_COLORS = {
    Severity.CRITICAL: "#dc2626",   # red-600
    Severity.WARNING:  "#d97706",   # amber-600
    Severity.INFO:     "#2563eb",   # accent blue
}

STATUS_COLORS = {
    TestStatus.PASS:  "#16a34a",   # green-600
    TestStatus.FAIL:  "#dc2626",   # red-600
    TestStatus.SKIP:  "#64748b",   # muted
    TestStatus.ERROR: "#9333ea",   # purple-600
}

STATUS_ICONS = {
    TestStatus.PASS:  "✅",
    TestStatus.FAIL:  "❌",
    TestStatus.SKIP:  "⏭",
    TestStatus.ERROR: "⚠️",
}

GRADE_COLORS = {
    "A+": "#16a34a", "A": "#16a34a",
    "B": "#84cc16",
    "C": "#f59e0b",
    "D": "#f97316",
    "F": "#dc2626",
}


def _load_logo_data_uri(logo_path: str | None) -> str | None:
    """Load SVG logo from file and return a data URI, or None if not found."""
    if not logo_path:
        return None
    p = Path(logo_path)
    if not p.exists():
        return None
    try:
        svg_bytes = p.read_bytes()
        b64 = base64.b64encode(svg_bytes).decode("ascii")
        return f"data:image/svg+xml;base64,{b64}"
    except Exception:
        return None


def _h(text: str) -> str:
    """HTML escape."""
    return html.escape(str(text) if text else "")


def generate_html(report: ReportData, output_path: str) -> str:
    """Generate standalone HTML report. Returns the HTML string."""

    # Branding
    branding = getattr(report, "branding", {}) or {}
    primary_color = branding.get("primary_color", "#1e3a5f")
    accent_color = branding.get("accent_color", "#2563eb")
    green_color = branding.get("green_color", "#16a34a")
    company = branding.get("company", report.company or "OCPP Compliance Tester")

    logo_uri = _load_logo_data_uri(branding.get("logo_path"))
    logo_color_uri = _load_logo_data_uri(branding.get("logo_color_path")) or logo_uri

    # Update STATUS_COLORS with branding green
    status_colors = dict(STATUS_COLORS)
    status_colors[TestStatus.PASS] = green_color

    # Severity colors use accent_color for INFO
    severity_colors = dict(SEVERITY_COLORS)
    severity_colors[Severity.INFO] = accent_color

    grade_color = GRADE_COLORS.get(report.grade, "#64748b")

    # Category rows
    category_rows = ""
    for cat in report.categories:
        effective = cat.total - cat.skipped
        pct = (cat.passed / effective * 100) if effective > 0 else 100.0
        bar_color = green_color if pct >= 90 else ("#f59e0b" if pct >= 60 else "#dc2626")
        critical_badge = (
            f'<span style="background:#dc2626;color:white;padding:2px 6px;'
            f'border-radius:4px;font-size:11px;">⚠ {cat.critical_failures} CRITICAL</span>'
            if cat.critical_failures > 0 else ""
        )
        category_rows += f"""
        <tr>
            <td style="padding:8px 12px;font-weight:500;color:#0f1f2e">{_h(cat.display_name)}</td>
            <td style="padding:8px 12px;text-align:center">{cat.total}</td>
            <td style="padding:8px 12px;text-align:center;color:{green_color};font-weight:600">{cat.passed}</td>
            <td style="padding:8px 12px;text-align:center;color:#dc2626;font-weight:600">{cat.failed}</td>
            <td style="padding:8px 12px;text-align:center;color:#64748b">{cat.skipped}</td>
            <td style="padding:8px 12px">
                <div style="background:#e2e8f0;border-radius:4px;height:8px;width:100%;min-width:100px">
                    <div style="background:{bar_color};width:{min(100,pct):.0f}%;height:8px;border-radius:4px"></div>
                </div>
                <small style="color:#64748b">{pct:.0f}%</small>
                {critical_badge}
            </td>
        </tr>"""

    # Test results table rows
    result_rows = ""
    for r in report.results:
        sc = status_colors.get(r.status, "#64748b")
        status_icon = STATUS_ICONS.get(r.status, "?")
        sev_color = severity_colors.get(r.severity, "#64748b")
        result_rows += f"""
        <tr style="border-bottom:1px solid #f1f5f9">
            <td style="padding:8px 12px;font-family:monospace;font-size:12px;color:#0f1f2e">{_h(r.test_name)}</td>
            <td style="padding:8px 12px;color:#64748b;font-size:12px">{_h(r.category)}</td>
            <td style="padding:8px 12px;font-weight:600;color:{sc}">{status_icon} {r.status.value}</td>
            <td style="padding:8px 12px;font-size:12px;color:{sev_color};font-weight:500">{r.severity.value}</td>
            <td style="padding:8px 12px;font-size:12px;color:#0f1f2e">{_h(r.message[:120])}</td>
            <td style="padding:8px 12px;font-size:11px;color:#94a3b8">{_h(r.spec_ref)}</td>
        </tr>"""

    # Failure detail sections
    failure_sections = ""
    for r in report.failures:
        sev_color = severity_colors.get(r.severity, "#64748b")
        status_icon = STATUS_ICONS.get(r.status, "?")

        exchanges_html = ""
        for ex in r.exchanges[:8]:
            direction_color = accent_color if ex.direction == "SENT" else green_color
            direction_label = "→ SENT" if ex.direction == "SENT" else "← RECEIVED"
            try:
                formatted = json.dumps(ex.payload, indent=2, ensure_ascii=False)
            except Exception:
                formatted = str(ex.payload)
            exchanges_html += f"""
                <div style="margin:8px 0">
                    <div style="font-weight:600;color:{direction_color};font-size:12px;margin-bottom:4px">
                        {direction_label} — {_h(ex.action)}
                        <span style="color:#94a3b8;font-weight:400;margin-left:8px">{_h(ex.timestamp)}</span>
                    </div>
                    <pre style="background:#f8fafc;border:1px solid #e2e8f0;padding:8px;
                                border-radius:4px;font-size:11px;overflow-x:auto;margin:0">{_h(formatted)}</pre>
                </div>"""

        failure_sections += f"""
        <div style="margin-bottom:32px;border:2px solid {sev_color};border-radius:8px;overflow:hidden">
            <div style="background:{sev_color};color:white;padding:12px 16px">
                <div style="font-size:18px;font-weight:700">{status_icon} {_h(r.test_name)}</div>
                <div style="font-size:13px;opacity:0.9;margin-top:4px">
                    {_h(r.category)} — {r.severity.value} — {_h(r.spec_ref)}
                </div>
            </div>
            <div style="padding:16px;background:#fff">
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
                    <div>
                        <div style="font-size:11px;font-weight:600;text-transform:uppercase;
                                    color:#64748b;margin-bottom:4px">Expected</div>
                        <div style="background:#f0fdf4;border:1px solid #bbf7d0;padding:8px;
                                    border-radius:4px;font-size:13px">{_h(r.expected) or _h(r.message)}</div>
                    </div>
                    <div>
                        <div style="font-size:11px;font-weight:600;text-transform:uppercase;
                                    color:#64748b;margin-bottom:4px">Actual</div>
                        <div style="background:#fef2f2;border:1px solid #fecaca;padding:8px;
                                    border-radius:4px;font-size:13px">{_h(r.actual) or _h(r.message)}</div>
                    </div>
                </div>
                {f'<div style="background:#fffbeb;border:1px solid #fde68a;padding:12px;border-radius:4px;margin-bottom:12px"><strong>🔧 Fix:</strong> {_h(r.fix_recommendation)}</div>' if r.fix_recommendation else ''}
                {f'<div><div style="font-size:11px;font-weight:600;text-transform:uppercase;color:#64748b;margin-bottom:8px">Message Exchanges</div>{exchanges_html}</div>' if exchanges_html else ''}
            </div>
        </div>"""

    # Test Criteria section
    criteria_cards = ""
    for crit in report.test_criteria:
        bullets = "".join(
            f"<li style='margin:4px 0;font-size:13px;color:#0f1f2e'>{_h(c)}</li>"
            for c in crit["pass_criteria"]
        )
        criteria_cards += f"""
        <div style="margin-bottom:16px;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">
            <div style="background:{primary_color};color:white;padding:10px 16px;
                        display:flex;justify-content:space-between;align-items:center;
                        flex-wrap:wrap;gap:8px">
                <span style="font-weight:700;font-size:15px">{_h(crit["display_name"])}</span>
                <span style="background:{accent_color};color:white;padding:3px 10px;border-radius:12px;
                             font-size:11px;font-weight:600;white-space:nowrap">{_h(crit["spec_ref"])}</span>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;background:white">
                <div style="padding:12px 16px;border-right:1px solid #e2e8f0;background:#f8fafc">
                    <div style="font-size:11px;font-weight:700;text-transform:uppercase;
                                color:#64748b;letter-spacing:0.5px;margin-bottom:6px">Description</div>
                    <p style="font-size:13px;color:#334155;line-height:1.5;margin:0">
                        <i>{_h(crit["description"])}</i>
                    </p>
                </div>
                <div style="padding:12px 16px;background:#f0fdf4">
                    <div style="font-size:11px;font-weight:700;text-transform:uppercase;
                                color:#3a6600;letter-spacing:0.5px;margin-bottom:6px">Pass Criteria</div>
                    <ul style="margin:0;padding-left:20px">{bullets}</ul>
                </div>
            </div>
        </div>"""

    # Message log table (last 100 entries)
    log_rows = ""
    for entry in report.message_log[-100:]:
        direction = entry.get("direction", "")
        dir_color = accent_color if direction == "OUT" else green_color
        dir_label = "→ OUT" if direction == "OUT" else "← IN"
        ts = entry.get("ts", "")
        raw = entry.get("raw", "")[:200]
        log_rows += f"""
        <tr style="border-bottom:1px solid #f1f5f9">
            <td style="padding:4px 8px;font-size:11px;color:#94a3b8;white-space:nowrap">{_h(ts[11:19] if len(ts) > 11 else ts)}</td>
            <td style="padding:4px 8px;font-size:11px;font-weight:600;color:{dir_color}">{dir_label}</td>
            <td style="padding:4px 8px;font-family:monospace;font-size:10px;color:#0f1f2e;word-break:break-all">{_h(raw)}</td>
        </tr>"""

    recommendations_html = ""
    for rec in report.recommendations:
        if rec.startswith("CRITICAL") or rec.startswith("WARNING") or rec.startswith("INFO"):
            recommendations_html += f"<div style='font-weight:600;margin-top:12px;color:{primary_color}'>{_h(rec)}</div>"
        else:
            recommendations_html += f"<div style='margin-left:16px;padding:4px 0;color:#0f1f2e'>{_h(rec)}</div>"

    # Optional logo HTML
    logo_img_html = (
        f'<img src="{logo_uri}" alt="{_h(company)}" style="height:44px;display:block;margin-bottom:20px">'
        if logo_uri else ""
    )
    footer_logo_html = (
        f'<img src="{logo_color_uri}" alt="{_h(company)}" style="height:28px;opacity:0.85">'
        if logo_color_uri else ""
    )

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_h(report.title)}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                color: #0f1f2e; background: #f8fafc; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ background: {primary_color}; color: #e2e8f0; padding: 10px 12px; text-align: left;
               font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }}
        .card {{ background: white; border-radius: 8px;
                 box-shadow: 0 1px 4px rgba(12,35,64,0.10); margin-bottom: 24px; overflow: hidden; }}
        .card-header {{ padding: 16px 20px; border-bottom: 3px solid {accent_color};
                        background: #f8fafc; }}
        .card-header h2 {{ color: {primary_color}; }}
        .card-body {{ padding: 20px; }}
        h1 {{ font-size: 28px; font-weight: 700; }}
        h2 {{ font-size: 20px; font-weight: 700; margin-bottom: 4px; }}
        h3 {{ font-size: 16px; font-weight: 600; }}
        a {{ color: {accent_color}; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        @media print {{ body {{ background: white; }} .no-print {{ display: none; }} }}
    </style>
</head>
<body>
<div class="container">

    <!-- Header -->
    <div class="card">
        <div style="background:linear-gradient(135deg,{primary_color} 0%,{primary_color} 60%,{accent_color} 100%);
                    color:white;padding:32px">
            {logo_img_html}
            <!-- Title + Grade row — flex, no overlap -->
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:24px;
                        flex-wrap:wrap">
                <!-- Left: title + meta -->
                <div style="flex:1;min-width:0">
                    <div style="font-size:12px;font-weight:600;text-transform:uppercase;
                                letter-spacing:1.5px;color:rgba(255,255,255,0.65);margin-bottom:8px">
                        OCPP Compliance Testing
                    </div>
                    <h1 style="color:white;font-size:24px;line-height:1.3;word-break:break-word">
                        {_h(report.title)}
                    </h1>
                    <div style="margin-top:10px;color:rgba(255,255,255,0.75);font-size:13px;
                                display:flex;flex-wrap:wrap;gap:12px">
                        <span>📅 {_h(report.test_date)}</span>
                        <span>⚡ OCPP {_h(report.ocpp_version)}</span>
                    </div>
                </div>
                <!-- Right: grade badge — fixed width, no clipping -->
                <div style="flex-shrink:0;text-align:center;background:rgba(255,255,255,0.12);
                            border:2px solid rgba(255,255,255,0.25);border-radius:12px;
                            padding:20px 28px;min-width:120px">
                    <div style="font-size:54px;font-weight:900;line-height:1;
                                color:{grade_color}">{report.grade}</div>
                    <div style="font-size:12px;color:rgba(255,255,255,0.80);margin-top:6px;
                                font-weight:500">{_h(report.grade_label)}</div>
                    <div style="font-size:22px;font-weight:700;margin-top:8px;color:white">
                        {report.pass_percentage:.1f}%
                    </div>
                </div>
            </div>
        </div>
        <!-- Charger info strip -->
        <div style="padding:20px;background:#f8fafc;border-top:1px solid #e2e8f0;
                    display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px">
            <div>
                <div style="font-size:11px;color:#64748b;text-transform:uppercase;
                            font-weight:600;letter-spacing:0.5px">Charger ID</div>
                <div style="font-weight:600;color:#0f1f2e;margin-top:2px">{_h(report.charger_id)}</div>
            </div>
            <div>
                <div style="font-size:11px;color:#64748b;text-transform:uppercase;
                            font-weight:600;letter-spacing:0.5px">Vendor</div>
                <div style="font-weight:600;color:#0f1f2e;margin-top:2px">{_h(report.charger_vendor)}</div>
            </div>
            <div>
                <div style="font-size:11px;color:#64748b;text-transform:uppercase;
                            font-weight:600;letter-spacing:0.5px">Model</div>
                <div style="font-weight:600;color:#0f1f2e;margin-top:2px">{_h(report.charger_model)}</div>
            </div>
            <div>
                <div style="font-size:11px;color:#64748b;text-transform:uppercase;
                            font-weight:600;letter-spacing:0.5px">Serial</div>
                <div style="font-weight:600;color:#0f1f2e;margin-top:2px">{_h(report.charger_serial)}</div>
            </div>
            <div>
                <div style="font-size:11px;color:#64748b;text-transform:uppercase;
                            font-weight:600;letter-spacing:0.5px">Firmware</div>
                <div style="font-weight:600;color:#0f1f2e;margin-top:2px">{_h(report.charger_firmware)}</div>
            </div>
            <div>
                <div style="font-size:11px;color:#64748b;text-transform:uppercase;
                            font-weight:600;letter-spacing:0.5px">OCPP Version</div>
                <div style="font-weight:600;color:#0f1f2e;margin-top:2px">{_h(report.ocpp_version)}</div>
            </div>
        </div>
    </div>

    <!-- Executive Summary -->
    <div class="card">
        <div class="card-header"><h2>Executive Summary</h2></div>
        <div class="card-body">
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
                        gap:16px;margin-bottom:24px">
                <div style="text-align:center;padding:16px;background:#f0fdf4;
                            border-radius:8px;border:1px solid #bbf7d0">
                    <div style="font-size:36px;font-weight:700;color:{green_color}">{report.passed_tests}</div>
                    <div style="font-size:13px;color:#3a6600;font-weight:600">PASSED</div>
                </div>
                <div style="text-align:center;padding:16px;background:#fef2f2;
                            border-radius:8px;border:1px solid #fecaca">
                    <div style="font-size:36px;font-weight:700;color:#dc2626">{report.failed_tests}</div>
                    <div style="font-size:13px;color:#b91c1c;font-weight:600">FAILED</div>
                </div>
                <div style="text-align:center;padding:16px;background:#f1f5f9;
                            border-radius:8px;border:1px solid #e2e8f0">
                    <div style="font-size:36px;font-weight:700;color:#64748b">{report.skipped_tests}</div>
                    <div style="font-size:13px;color:#475569;font-weight:600">SKIPPED</div>
                </div>
                <div style="text-align:center;padding:16px;background:#e8edf5;
                            border-radius:8px;border:1px solid #c0d0e8">
                    <div style="font-size:36px;font-weight:700;color:{primary_color}">{report.total_tests}</div>
                    <div style="font-size:13px;color:{primary_color};font-weight:600">TOTAL</div>
                </div>
            </div>
            <table>
                <thead><tr>
                    <th>Category</th><th>Total</th><th>Passed</th>
                    <th>Failed</th><th>Skipped</th><th>Compliance</th>
                </tr></thead>
                <tbody>{category_rows}</tbody>
            </table>
        </div>
    </div>

    <!-- Recommendations -->
    {f'''<div class="card">
        <div class="card-header"><h2>Recommendations for Manufacturer</h2></div>
        <div class="card-body" style="font-size:14px;line-height:1.6">
            {recommendations_html if recommendations_html else "<p style='color:#64748b'>No issues found.</p>"}
        </div>
    </div>''' if report.failures else ''}

    <!-- Test Criteria & Standards -->
    <div class="card">
        <div class="card-header">
            <h2>Test Criteria &amp; Standards</h2>
            <p style="color:#64748b;font-size:13px;margin-top:4px">
                Each test category maps to an OCPP 1.6 specification section.
                This table describes the validation logic and pass/fail criteria applied.
            </p>
        </div>
        <div class="card-body">
            {criteria_cards}
        </div>
    </div>

    <!-- All Test Results -->
    <div class="card">
        <div class="card-header"><h2>All Test Results</h2></div>
        <div class="card-body" style="overflow-x:auto">
            <table>
                <thead><tr>
                    <th>Test Name</th><th>Category</th><th>Status</th>
                    <th>Severity</th><th>Message</th><th>Spec Ref</th>
                </tr></thead>
                <tbody>{result_rows}</tbody>
            </table>
        </div>
    </div>

    <!-- Failure Details -->
    {f'''<div class="card">
        <div class="card-header">
            <h2>Deviation Details ({len(report.failures)} failures)</h2>
            <p style="color:#64748b;font-size:13px;margin-top:4px">
                Detailed analysis of each test failure with expected vs actual behavior,
                raw message exchanges, and fix recommendations.
            </p>
        </div>
        <div class="card-body">
            {failure_sections}
        </div>
    </div>''' if report.failures else ''}

    <!-- Message Log -->
    <div class="card">
        <div class="card-header">
            <h2>Message Log (last 100 messages)</h2>
            <p style="color:#64748b;font-size:13px;margin-top:4px">
                Full bidirectional OCPP message log captured during testing.
                Total: {len(report.message_log)} messages.
            </p>
        </div>
        <div class="card-body" style="overflow-x:auto">
            <table>
                <thead><tr><th>Time</th><th>Dir</th><th>Message</th></tr></thead>
                <tbody>{log_rows}</tbody>
            </table>
        </div>
    </div>

    <!-- Footer -->
    <div style="text-align:center;padding:24px 16px;margin-top:8px;
                border-top:3px solid {primary_color}">
        {"<div style='display:flex;align-items:center;justify-content:center;gap:12px;flex-wrap:wrap;margin-bottom:8px'>" + footer_logo_html + "</div>" if footer_logo_html else ""}
        <div style="color:#64748b;font-size:12px">
            <strong style="color:{primary_color}">{_h(company)}</strong> · OCPP Compliance Tester ·
            Generated {_h(report.generated_at)}
        </div>
    </div>

</div>
</body>
</html>"""

    Path(output_path).write_text(html_content, encoding="utf-8")
    return html_content
