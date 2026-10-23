from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# AXIOM palette (same as the portal and the Workbench screens)
ACCENT = colors.HexColor("#663BFF")
DARK = colors.HexColor("#182033")
LIGHT = colors.HexColor("#F7F8FA")
BORDER = colors.HexColor("#E4E7EC")
MUTED = colors.HexColor("#667085")


_FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
_REGULAR = _FONT_DIR / "DejaVuSans.ttf"
_BOLD = _FONT_DIR / "DejaVuSans-Bold.ttf"

if _REGULAR.exists() and _BOLD.exists():
    try:
        pdfmetrics.registerFont(TTFont("EtexSans", str(_REGULAR)))
        pdfmetrics.registerFont(TTFont("EtexSansBold", str(_BOLD)))
        FONT = "EtexSans"
        FONT_BOLD = "EtexSansBold"
    except Exception:
        FONT = "Helvetica"
        FONT_BOLD = "Helvetica-Bold"
else:
    FONT = "Helvetica"
    FONT_BOLD = "Helvetica-Bold"


SECTION_LABELS = {
    "request_information": "Request Information",
    "general_data": "General Data",
    "company_code": "Company Code",
    "sales_distribution": "Sales & Distribution",
    "partner_functions": "Partner Functions",
    "credit_management": "Credit Management",
}


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (list, tuple)):
        return ", ".join(_clean(item) for item in value)
    return str(value).strip()


def _label(key: Any) -> str:
    special = {
        "id": "ID",
        "vat": "VAT",
        "iban": "IBAN",
        "sap": "SAP",
        "mdm": "MDM",
        "url": "URL",
        "topdesk": "TOPdesk",
    }
    words: list[str] = []
    for part in str(key).replace("-", "_").split("_"):
        lower = part.lower()
        words.append(special.get(lower, part.capitalize()))
    return " ".join(words)


def _p(value: Any, style: ParagraphStyle) -> Paragraph:
    text = escape(_clean(value)).replace("\n", "<br/>") or "-"
    return Paragraph(text, style)


def _table_style(header: bool = False) -> TableStyle:
    commands: list[tuple] = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.45, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        commands.extend(
            [
                ("BACKGROUND", (0, 0), (-1, 0), DARK),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
            ]
        )
    return TableStyle(commands)


def _section_title(text: str, styles: dict[str, ParagraphStyle]) -> KeepTogether:
    return KeepTogether(
        [
            Spacer(1, 3 * mm),
            Paragraph(escape(text), styles["section"]),
            Spacer(1, 1.5 * mm),
        ]
    )


def _simple_section(
    data: dict[str, Any],
    *,
    body_style: ParagraphStyle,
) -> Table | None:
    rows: list[list[Paragraph]] = []
    for key, value in data.items():
        if isinstance(value, (dict, list, tuple)):
            continue
        text = _clean(value)
        if not text:
            continue
        rows.append(
            [
                _p(_label(key), body_style),
                _p(text, body_style),
            ]
        )
    if not rows:
        return None
    table = Table(rows, colWidths=[55 * mm, 120 * mm], repeatRows=0)
    table.setStyle(_table_style(False))
    return table


def _general_data_table(
    data: dict[str, Any],
    *,
    body_style: ParagraphStyle,
    small_style: ParagraphStyle,
) -> Table | None:
    rows: list[list[Paragraph]] = [
        [
            _p("Field", small_style),
            _p("SAP Field", small_style),
            _p("Current", small_style),
            _p("Requested", small_style),
        ]
    ]
    for field_key, item in data.items():
        if not isinstance(item, dict):
            continue
        rows.append(
            [
                _p(item.get("label") or _label(field_key), body_style),
                _p(item.get("sap_field") or "", body_style),
                _p(item.get("current_value") or "", body_style),
                _p(item.get("requested_value") or "", body_style),
            ]
        )
    if len(rows) == 1:
        return None
    table = Table(
        rows,
        colWidths=[48 * mm, 25 * mm, 47 * mm, 55 * mm],
        repeatRows=1,
    )
    table.setStyle(_table_style(True))
    return table


def build_request_pdf(
    request: dict[str, Any],
    *,
    ticket_number: str = "",
) -> bytes:
    """Return a printable PDF summary of one submitted customer request."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=17 * mm,
        leftMargin=17 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Customer request {_clean(request.get('request_id'))}",
        author="Customer Master Data Workbench",
    )

    base = getSampleStyleSheet()
    styles: dict[str, ParagraphStyle] = {
        "title": ParagraphStyle(
            "EtexTitle",
            parent=base["Title"],
            fontName=FONT_BOLD,
            fontSize=18,
            leading=22,
            textColor=DARK,
            alignment=TA_LEFT,
            spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "EtexSubtitle",
            parent=base["Normal"],
            fontName=FONT,
            fontSize=8.5,
            leading=11,
            textColor=MUTED,
            spaceAfter=8,
        ),
        "section": ParagraphStyle(
            "EtexSection",
            parent=base["Heading2"],
            fontName=FONT_BOLD,
            fontSize=11.5,
            leading=14,
            textColor=DARK,
            spaceBefore=2,
            spaceAfter=2,
        ),
        "body": ParagraphStyle(
            "EtexBody",
            parent=base["Normal"],
            fontName=FONT,
            fontSize=8.5,
            leading=11,
            textColor=DARK,
        ),
        "small": ParagraphStyle(
            "EtexSmall",
            parent=base["Normal"],
            fontName=FONT_BOLD,
            fontSize=7.5,
            leading=9,
            textColor=colors.white,
        ),
        "comment": ParagraphStyle(
            "EtexComment",
            parent=base["Normal"],
            fontName=FONT,
            fontSize=8.5,
            leading=11,
            textColor=DARK,
            backColor=LIGHT,
            borderColor=BORDER,
            borderWidth=0.5,
            borderPadding=6,
            spaceBefore=4,
            spaceAfter=5,
        ),
    }

    request_id = _clean(request.get("request_id")) or "Customer Request"
    status = _clean(request.get("display_status") or request.get("status"))
    payload = request.get("payload") if isinstance(request.get("payload"), dict) else {}
    internal = payload.get("workbench_internal", {})
    if not isinstance(internal, dict):
        internal = {}
    ticket = _clean(ticket_number) or _clean(internal.get("topdesk_ticket_number"))

    story: list[Any] = []
    story.append(Paragraph("Customer Master Data Request", styles["title"]))
    story.append(
        Paragraph(
            escape(
                "Structured request summary for TOPdesk / Master Data review."
            ),
            styles["subtitle"],
        )
    )

    overview = [
        ["Request ID", request_id, "TOPdesk Ticket", ticket or "-"],
        ["Customer", _clean(request.get("customer_name")), "Customer ID", _clean(request.get("customer_id"))],
        ["Request Type", _clean(request.get("request_type")), "Status", status],
        ["Company Code", _clean(request.get("company_code")), "Sales Org", _clean(request.get("sales_org"))],
        ["Requested By", _clean(request.get("requested_by")), "Requested At", _clean(request.get("requested_at"))],
    ]
    overview_rows: list[list[Paragraph]] = []
    for left_label, left_value, right_label, right_value in overview:
        overview_rows.append(
            [
                _p(left_label, styles["body"]),
                _p(left_value, styles["body"]),
                _p(right_label, styles["body"]),
                _p(right_value, styles["body"]),
            ]
        )
    overview_table = Table(
        overview_rows,
        colWidths=[29 * mm, 58 * mm, 31 * mm, 57 * mm],
    )
    overview_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.45, BORDER),
                ("BACKGROUND", (0, 0), (0, -1), LIGHT),
                ("BACKGROUND", (2, 0), (2, -1), LIGHT),
                ("FONTNAME", (0, 0), (0, -1), FONT_BOLD),
                ("FONTNAME", (2, 0), (2, -1), FONT_BOLD),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(overview_table)

    # Change requests list every picked field with its current value
    changes = payload.get("change_request")
    if isinstance(changes, list) and changes:
        story.append(_section_title("Requested Changes", styles))
        change_rows = [
            [
                _p("Section", styles["small"]),
                _p("Field", styles["small"]),
                _p("Current", styles["small"]),
                _p("Requested", styles["small"]),
            ]
        ]
        for item in changes:
            if not isinstance(item, dict):
                continue
            change_rows.append(
                [
                    _p(item.get("section") or "", styles["body"]),
                    _p(item.get("field_label") or _label(item.get("field_key")), styles["body"]),
                    _p(item.get("current_value") or "-", styles["body"]),
                    _p(item.get("requested_value") or "-", styles["body"]),
                ]
            )
        change_table = Table(
            change_rows,
            colWidths=[35 * mm, 48 * mm, 46 * mm, 46 * mm],
            repeatRows=1,
        )
        change_table.setStyle(_table_style(True))
        story.append(change_table)

    comments = payload.get("section_comments", {})
    if not isinstance(comments, dict):
        comments = {}

    section_order = [
        "request_information",
        "general_data",
        "company_code",
        "sales_distribution",
        "partner_functions",
        "credit_management",
    ]

    for section in section_order:
        if section not in payload:
            continue
        data = payload.get(section, {})
        if not isinstance(data, dict):
            continue

        story.append(_section_title(SECTION_LABELS.get(section, _label(section)), styles))
        if section == "general_data":
            section_table = _general_data_table(
                data,
                body_style=styles["body"],
                small_style=styles["small"],
            )
        else:
            section_table = _simple_section(data, body_style=styles["body"])

        if section_table is not None:
            story.append(section_table)
        else:
            story.append(Paragraph("No values submitted.", styles["subtitle"]))

        comment = _clean(comments.get(section))
        if comment:
            story.append(
                Paragraph(
                    "<b>Requester comment:</b><br/>"
                    + escape(comment).replace("\n", "<br/>"),
                    styles["comment"],
                )
            )

    attachments = payload.get("attachments", [])
    if isinstance(attachments, list) and attachments:
        story.append(_section_title("Attachments", styles))
        attachment_rows = [[_p("File", styles["small"]), _p("Size", styles["small"])]]
        for item in attachments:
            if not isinstance(item, dict):
                continue
            name = _clean(item.get("name"))
            try:
                size_kb = int(item.get("size_bytes") or 0) / 1024
                size = f"{size_kb:.0f} KB"
            except (TypeError, ValueError):
                size = ""
            attachment_rows.append([_p(name, styles["body"]), _p(size, styles["body"])])
        attachment_table = Table(attachment_rows, colWidths=[140 * mm, 35 * mm], repeatRows=1)
        attachment_table.setStyle(_table_style(True))
        story.append(attachment_table)

    story.append(Spacer(1, 5 * mm))
    footer_text = "Generated from Customer Master Data Workbench. Communication and ticket handling remain in TOPdesk."
    story.append(Paragraph(escape(footer_text), styles["subtitle"]))

    def _page(canvas, document):
        canvas.saveState()
        width, _ = A4
        canvas.setStrokeColor(ACCENT)
        canvas.setLineWidth(2)
        canvas.line(17 * mm, 11 * mm, width - 17 * mm, 11 * mm)
        canvas.setFont(FONT, 7)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(width - 17 * mm, 6.5 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_page, onLaterPages=_page)
    return buffer.getvalue()
