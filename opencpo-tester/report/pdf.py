"""
PDF Report Generator using ReportLab.
Professional layout with configurable branding.
Branding (colors, logo, company) is read from report.branding, not hardcoded.
"""
import base64
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from tests.base import TestStatus, Severity
from report.generator import ReportData, GRADE_COLORS

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm, cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, HRFlowable, KeepTogether
    )
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


# Default brand colors (overridden by report.branding at runtime)
_DEFAULT_PRIMARY = "#1e3a5f"
_DEFAULT_ACCENT  = "#2563eb"
_DEFAULT_GREEN   = "#16a34a"

COLOR_RED   = None  # set in generate_pdf
COLOR_AMBER = None
COLOR_GRAY  = None
COLOR_LIGHT_GRAY = None

STATUS_LABELS = {
    TestStatus.PASS: "PASS ✓",
    TestStatus.FAIL: "FAIL ✗",
    TestStatus.SKIP: "SKIP →",
    TestStatus.ERROR: "ERR !",
}


def generate_pdf(report: ReportData, output_path: str) -> bool:
    """Generate PDF report. Returns True on success."""
    if not REPORTLAB_AVAILABLE:
        print("WARNING: reportlab not installed — skipping PDF generation. Install with: pip install reportlab")
        return False

    # ── Branding ────────────────────────────────────────────────────────
    branding = getattr(report, "branding", {}) or {}
    primary_hex   = branding.get("primary_color", _DEFAULT_PRIMARY)
    accent_hex    = branding.get("accent_color",  _DEFAULT_ACCENT)
    green_hex     = branding.get("green_color",   _DEFAULT_GREEN)
    company       = branding.get("company", report.company or "OCPP Compliance Tester")

    BRAND_BLUE       = colors.HexColor(primary_hex)
    BRAND_LIGHT_BLUE = colors.HexColor(accent_hex)
    COLOR_GREEN      = colors.HexColor(green_hex)
    COLOR_RED        = colors.HexColor("#dc2626")
    COLOR_AMBER      = colors.HexColor("#d97706")
    COLOR_GRAY       = colors.HexColor("#64748b")
    COLOR_LIGHT_GRAY = colors.HexColor("#f8fafc")

    SEVERITY_COLORS_RL = {
        Severity.CRITICAL: COLOR_RED,
        Severity.WARNING: COLOR_AMBER,
        Severity.INFO: BRAND_LIGHT_BLUE,
    }
    STATUS_COLORS_RL = {
        TestStatus.PASS: COLOR_GREEN,
        TestStatus.FAIL: COLOR_RED,
        TestStatus.SKIP: COLOR_GRAY,
        TestStatus.ERROR: colors.HexColor("#9333ea"),
    }
    GRADE_COLORS_RL = {
        "A+": COLOR_GREEN, "A": COLOR_GREEN,
        "B": colors.HexColor("#84cc16"),
        "C": COLOR_AMBER,
        "D": colors.HexColor("#f97316"),
        "F": COLOR_RED,
    }

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=20*mm,
        leftMargin=20*mm,
        topMargin=20*mm,
        bottomMargin=20*mm,
        title=report.title,
        author=company,
    )

    styles = getSampleStyleSheet()
    story = []

    def h1(text):
        return Paragraph(text, ParagraphStyle(
            "h1", parent=styles["Heading1"],
            textColor=BRAND_BLUE, fontSize=20, spaceAfter=6
        ))

    def h2(text):
        return Paragraph(text, ParagraphStyle(
            "h2", parent=styles["Heading2"],
            textColor=BRAND_BLUE, fontSize=14, spaceAfter=4
        ))

    def h3(text):
        return Paragraph(text, ParagraphStyle(
            "h3", parent=styles["Heading3"],
            textColor=BRAND_BLUE, fontSize=11, spaceAfter=2
        ))

    def body(text, **kwargs):
        return Paragraph(text or "", ParagraphStyle(
            "body", parent=styles["Normal"],
            fontSize=9, spaceAfter=2, **kwargs
        ))

    def mono(text):
        return Paragraph(text or "", ParagraphStyle(
            "mono", parent=styles["Normal"],
            fontName="Courier", fontSize=7.5,
            spaceAfter=0, leading=11
        ))

    # ── Cover Page ────────────────────────────────────────────────────────

    story.append(Spacer(1, 1*cm))

    # Header bar with company name
    header_data = [[
        Paragraph(company, ParagraphStyle(
            "company", parent=styles["Normal"],
            textColor=colors.white, fontSize=14,
            fontName="Helvetica-Bold", spaceAfter=0,
        )),
        Paragraph("OCPP Compliance Testing", ParagraphStyle(
            "subtitle", parent=styles["Normal"],
            textColor=colors.HexColor("#80d8f2"), fontSize=10,
            fontName="Helvetica", alignment=TA_RIGHT,
        )),
    ]]
    header_table = Table(header_data, colWidths=["50%", "50%"])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BRAND_BLUE),
        ("PADDING", (0, 0), (-1, -1), 14),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(header_table)

    # Accent line
    story.append(HRFlowable(width="100%", thickness=4, color=BRAND_LIGHT_BLUE))
    story.append(Spacer(1, 0.8*cm))

    # Title — its own block, no overlap possible
    story.append(Paragraph(report.title, ParagraphStyle(
        "title", parent=styles["Normal"],
        textColor=BRAND_BLUE, fontSize=22,
        fontName="Helvetica-Bold", spaceAfter=6, leading=28
    )))
    story.append(Spacer(1, 0.4*cm))

    # Grade box — separate row, full width
    grade_color = GRADE_COLORS_RL.get(report.grade, COLOR_GRAY)
    grade_data = [[
        Paragraph(f"Grade: {report.grade}", ParagraphStyle(
            "grade_label", parent=styles["Normal"],
            textColor=colors.white, fontSize=32, fontName="Helvetica-Bold",
            alignment=TA_CENTER,
        )),
        Paragraph(
            f"<b>{report.pass_percentage:.1f}%</b> tests passed<br/>"
            f"{report.passed_tests} / {report.total_tests - report.skipped_tests} tests<br/>"
            f"<i>{report.grade_label}</i>",
            ParagraphStyle("grade_sub", parent=styles["Normal"],
                           textColor=colors.white, fontSize=11, alignment=TA_CENTER)
        ),
    ]]
    grade_table = Table(grade_data, colWidths=["35%", "65%"])
    grade_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), grade_color),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 16),
    ]))
    story.append(grade_table)
    story.append(Spacer(1, 0.5*cm))

    # Charger details
    charger_info = [
        ["Field", "Value"],
        ["Charger ID", report.charger_id or "—"],
        ["Vendor", report.charger_vendor or "—"],
        ["Model", report.charger_model or "—"],
        ["Serial Number", report.charger_serial or "—"],
        ["Firmware Version", report.charger_firmware or "—"],
        ["OCPP Version", report.ocpp_version or "—"],
        ["Test Date", report.test_date or "—"],
        ["Generated By", company],
    ]
    charger_table = Table(charger_info, colWidths=["35%", "65%"])
    charger_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 1), (0, -1), COLOR_LIGHT_GRAY),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
    ]))
    story.append(charger_table)
    story.append(PageBreak())

    # ── Executive Summary ─────────────────────────────────────────────────

    story.append(h1("Executive Summary"))
    story.append(HRFlowable(width="100%", thickness=1, color=BRAND_LIGHT_BLUE))
    story.append(Spacer(1, 0.3*cm))

    # Stats row — use Paragraph cells so numbers and labels don't overlap
    def _stat_cell(number, label, num_color):
        return [Paragraph(
            f'<font size="28" color="{num_color.hexval() if hasattr(num_color, "hexval") else "#000000"}"><b>{number}</b></font>',
            ParagraphStyle("stat_num", parent=styles["Normal"],
                           alignment=TA_CENTER, spaceAfter=2, leading=32)
        ), Paragraph(
            f'<font size="9">{label}</font>',
            ParagraphStyle("stat_label", parent=styles["Normal"],
                           alignment=TA_CENTER, spaceAfter=0)
        )]

    def _stat_cell_p(number, label, num_hex, bg_hex, label_hex):
        """Return a nested 1-col table so number and label stack cleanly."""
        inner = Table([
            [Paragraph(f'<b>{number}</b>', ParagraphStyle(
                "sn", parent=styles["Normal"],
                fontSize=26, textColor=colors.HexColor(num_hex),
                alignment=TA_CENTER, leading=30, spaceAfter=0,
            ))],
            [Paragraph(label, ParagraphStyle(
                "sl", parent=styles["Normal"],
                fontSize=8, textColor=colors.HexColor(label_hex),
                fontName="Helvetica-Bold",
                alignment=TA_CENTER, leading=10, spaceAfter=0,
            ))],
        ], colWidths=["100%"])
        inner.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg_hex)),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("PADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (0, 0), 14),
            ("BOTTOMPADDING", (1, 0), (1, 0), 14),
        ]))
        return inner

    stats_data = [[
        _stat_cell_p(report.passed_tests,  "PASSED",  "#166534", "#f0fdf4", "#166534"),
        _stat_cell_p(report.failed_tests,  "FAILED",  "#991b1b", "#fef2f2", "#991b1b"),
        _stat_cell_p(report.skipped_tests, "SKIPPED", "#475569", "#f8fafc", "#475569"),
        _stat_cell_p(report.total_tests,   "TOTAL",   primary_hex, "#eff6ff", primary_hex),
    ]]
    stats_table = Table(stats_data, colWidths=["25%", "25%", "25%", "25%"])
    stats_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(stats_table)
    story.append(Spacer(1, 0.4*cm))

    # Category table
    story.append(h2("Results by Category"))
    cat_header = ["Category", "Total", "Passed", "Failed", "Skipped", "Pass %"]
    cat_rows = [cat_header]
    for cat in report.categories:
        eff = cat.total - cat.skipped
        pct = f"{cat.passed/eff*100:.0f}%" if eff > 0 else "N/A"
        critical_note = f" ⚠ {cat.critical_failures}×CRITICAL" if cat.critical_failures > 0 else ""
        cat_rows.append([
            cat.display_name + critical_note,
            str(cat.total), str(cat.passed), str(cat.failed), str(cat.skipped), pct
        ])

    cat_table = Table(cat_rows, colWidths=["35%", "10%", "12%", "12%", "12%", "19%"])
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
    ]
    for i, cat in enumerate(report.categories, 1):
        if cat.failed > 0 and cat.critical_failures > 0:
            style.append(("TEXTCOLOR", (0, i), (0, i), COLOR_RED))
            style.append(("FONTNAME", (0, i), (0, i), "Helvetica-Bold"))
        if cat.failed > 0:
            style.append(("TEXTCOLOR", (3, i), (3, i), COLOR_RED))
            style.append(("FONTNAME", (3, i), (3, i), "Helvetica-Bold"))

    cat_table.setStyle(TableStyle(style))
    story.append(cat_table)
    story.append(PageBreak())

    # ── Test Criteria & Standards ─────────────────────────────────────────

    story.append(h1("Test Criteria & Standards"))
    story.append(body(
        "This section describes what each test category validates, the relevant OCPP 1.6 "
        "specification sections, and the pass/fail criteria applied during testing."
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=BRAND_LIGHT_BLUE))
    story.append(Spacer(1, 0.3*cm))

    for crit in report.test_criteria:
        elems = []

        # Header: category name + spec ref
        header_data = [[
            Paragraph(crit["display_name"], ParagraphStyle(
                "crit_title", parent=styles["Normal"],
                textColor=colors.white, fontSize=11, fontName="Helvetica-Bold",
            )),
            Paragraph(crit["spec_ref"], ParagraphStyle(
                "crit_spec", parent=styles["Normal"],
                textColor=colors.HexColor("#b3ecfa"), fontSize=8,
                alignment=TA_RIGHT,
            )),
        ]]
        hdr_t = Table(header_data, colWidths=["65%", "35%"])
        hdr_t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), BRAND_BLUE),
            ("PADDING", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elems.append(hdr_t)

        # Description + criteria in two columns
        criteria_bullets = "<br/>".join(
            f"• {c}" for c in crit["pass_criteria"]
        )
        detail_data = [[
            Paragraph(
                f"<i>{crit['description']}</i>",
                ParagraphStyle("crit_desc", parent=styles["Normal"],
                               fontSize=8, textColor=colors.HexColor("#334155"))
            ),
            Paragraph(
                f"<b>Pass criteria:</b><br/>{criteria_bullets}",
                ParagraphStyle("crit_crit", parent=styles["Normal"],
                               fontSize=8, textColor=colors.HexColor("#0f172a"),
                               leading=12)
            ),
        ]]
        detail_t = Table(detail_data, colWidths=["38%", "62%"])
        detail_t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#f8fafc")),
            ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#f0fdf4")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("PADDING", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        elems.append(detail_t)
        elems.append(Spacer(1, 0.2*cm))
        story.append(KeepTogether(elems))

    story.append(PageBreak())

    # ── Per-Category Results ──────────────────────────────────────────────

    story.append(h1("Test Results"))
    story.append(HRFlowable(width="100%", thickness=1, color=BRAND_LIGHT_BLUE))
    story.append(Spacer(1, 0.3*cm))

    for cat in report.categories:
        cat_results = [r for r in report.results if r.category == cat.name]
        if not cat_results:
            continue

        story.append(h2(cat.display_name))

        rows = [["Test", "Status", "Severity", "Message"]]
        for r in cat_results:
            status_label = STATUS_LABELS.get(r.status, r.status.value)
            rows.append([
                r.test_name,
                status_label,
                r.severity.value,
                (r.message or "")[:80],
            ])

        t = Table(rows, colWidths=["36%", "12%", "13%", "39%"])
        ts = TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT_BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e5e7eb")),
            ("PADDING", (0, 0), (-1, -1), 5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
        ])
        for i, r in enumerate(cat_results, 1):
            sc = STATUS_COLORS_RL.get(r.status, COLOR_GRAY)
            ts.add("TEXTCOLOR", (1, i), (1, i), sc)
            ts.add("FONTNAME", (1, i), (1, i), "Helvetica-Bold")
            sev_c = SEVERITY_COLORS_RL.get(r.severity, COLOR_GRAY)
            ts.add("TEXTCOLOR", (2, i), (2, i), sev_c)

        t.setStyle(ts)
        story.append(t)
        story.append(Spacer(1, 0.3*cm))

    story.append(PageBreak())

    # ── Deviation Details ──────────────────────────────────────────────────

    if report.failures:
        story.append(h1(f"Deviation Details ({len(report.failures)} Failures)"))
        story.append(body(
            "This section details each test failure with expected vs actual behavior, "
            "raw OCPP message exchanges, spec references, and manufacturer fix recommendations."
        ))
        story.append(HRFlowable(width="100%", thickness=1, color=BRAND_LIGHT_BLUE))
        story.append(Spacer(1, 0.3*cm))

        for r in report.failures:
            sev_color = SEVERITY_COLORS_RL.get(r.severity, COLOR_GRAY)

            elems = []

            # Title bar
            title_data = [[
                Paragraph(f"[{r.severity.value}] {r.test_name}", ParagraphStyle(
                    "fail_title", parent=styles["Normal"],
                    textColor=colors.white, fontSize=11, fontName="Helvetica-Bold"
                )),
                Paragraph(f"{r.status.value} · {r.spec_ref}", ParagraphStyle(
                    "fail_meta", parent=styles["Normal"],
                    textColor=colors.white, fontSize=8, alignment=TA_RIGHT
                )),
            ]]
            title_t = Table(title_data, colWidths=["65%", "35%"])
            title_t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), sev_color),
                ("PADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            elems.append(title_t)

            # Expected / Actual
            exp_act_data = [[
                Paragraph(
                    f"<b>Expected:</b><br/>{r.expected or r.message or '—'}",
                    ParagraphStyle("exp", parent=styles["Normal"], fontSize=8,
                                   backColor=colors.HexColor("#f0fdf4"))
                ),
                Paragraph(
                    f"<b>Actual:</b><br/>{r.actual or r.message or '—'}",
                    ParagraphStyle("act", parent=styles["Normal"], fontSize=8,
                                   backColor=colors.HexColor("#fef2f2"))
                ),
            ]]
            exp_act = Table(exp_act_data, colWidths=["50%", "50%"])
            exp_act.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#f0fdf4")),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#fef2f2")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                ("PADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            elems.append(exp_act)

            # Fix recommendation
            if r.fix_recommendation:
                fix_data = [[
                    Paragraph(
                        f"🔧 <b>Fix Recommendation:</b> {r.fix_recommendation}",
                        ParagraphStyle("fix", parent=styles["Normal"], fontSize=8,
                                       textColor=colors.HexColor("#92400e"))
                    )
                ]]
                fix_t = Table(fix_data, colWidths=["100%"])
                fix_t.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffbeb")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#fde68a")),
                    ("PADDING", (0, 0), (-1, -1), 8),
                ]))
                elems.append(fix_t)

            # Message exchanges
            for ex in r.exchanges[:5]:
                try:
                    formatted = json.dumps(ex.payload, indent=2, ensure_ascii=False)
                except Exception:
                    formatted = str(ex.payload)

                dir_label = f"→ {ex.action} (SENT)" if ex.direction == "SENT" else f"← {ex.action} (RECEIVED)"
                dir_color = colors.HexColor("#1d4ed8") if ex.direction == "SENT" else COLOR_GREEN

                msg_data = [[
                    Paragraph(dir_label, ParagraphStyle(
                        "dir", parent=styles["Normal"],
                        textColor=dir_color, fontSize=8, fontName="Helvetica-Bold"
                    )),
                    mono(formatted[:500]),
                ]]
                msg_t = Table(msg_data, colWidths=["25%", "75%"])
                msg_t.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
                    ("PADDING", (0, 0), (-1, -1), 6),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]))
                elems.append(msg_t)

            elems.append(Spacer(1, 0.2*cm))
            story.append(KeepTogether(elems))

        story.append(PageBreak())

    # ── Recommendations ────────────────────────────────────────────────────

    if report.recommendations:
        story.append(h1("Manufacturer Recommendations"))
        story.append(HRFlowable(width="100%", thickness=1, color=BRAND_LIGHT_BLUE))
        story.append(Spacer(1, 0.2*cm))
        for rec in report.recommendations:
            if rec.startswith("CRITICAL") or rec.startswith("WARNING") or rec.startswith("INFO"):
                story.append(body(f"<b>{rec}</b>"))
            elif rec.startswith("  •"):
                story.append(body(f"  {rec.strip()}"))
            else:
                story.append(body(rec))
        story.append(PageBreak())

    # ── Message Log Appendix ──────────────────────────────────────────────

    story.append(h1("Appendix: Full Message Log"))
    story.append(body(f"Total messages: {len(report.message_log)}. Showing all entries."))
    story.append(HRFlowable(width="100%", thickness=1, color=BRAND_LIGHT_BLUE))
    story.append(Spacer(1, 0.2*cm))

    log_header = [["Time", "Dir", "Message (truncated)"]]
    log_rows_data = []
    for entry in report.message_log:
        ts = entry.get("ts", "")
        time_str = ts[11:19] if len(ts) > 11 else ts
        direction = entry.get("direction", "")
        raw = (entry.get("raw") or "")[:150]
        log_rows_data.append([time_str, direction, raw])

    # Batch into one table
    all_log = log_header + log_rows_data
    if len(all_log) > 1:
        log_table = Table(all_log, colWidths=["14%", "8%", "78%"])
        log_style = TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Courier"),
            ("FONTSIZE", (0, 0), (-1, -1), 6.5),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e5e7eb")),
            ("PADDING", (0, 0), (-1, -1), 3),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
        ])
        # Color direction column
        for i, entry in enumerate(report.message_log, 1):
            if i < len(all_log):
                d = entry.get("direction", "")
                if d == "OUT":
                    log_style.add("TEXTCOLOR", (1, i), (1, i), BRAND_LIGHT_BLUE)
                else:
                    log_style.add("TEXTCOLOR", (1, i), (1, i), COLOR_GREEN)
        log_table.setStyle(log_style)
        story.append(log_table)

    doc.build(story)
    return True
