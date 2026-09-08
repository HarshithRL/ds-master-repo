"""Comparison workbook. Direct = France P×Q pack. Indirect = SWIFT BAFO pack.

W8: cells come from SQL `evidence` + `pricing_line`. No LLM in this path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font

from ai_brain.core.procurement_ai.packs import store
from ai_brain.core.procurement_ai.packs.matrix_direct import write_direct
from ai_brain.core.procurement_ai.packs.matrix_extract import empty_direct, empty_indirect
from ai_brain.core.procurement_ai.packs.matrix_from_evidence import (
    insights_from_source,
    load_matrix_source,
    matrix_from_source,
)
from ai_brain.core.procurement_ai.packs.matrix_indirect import write_indirect
from ai_brain.core.procurement_ai.packs.matrix_schema import DirectMatrix, IndirectMatrix
from ai_brain.core.procurement_ai.packs.xlsx_style import COVER_FIELDS, autosize, header_row
from ai_brain.core.procurement_ai.process_type import DIRECT_TG
from shared.logger_global import get_logger

log = get_logger(__name__, service="ai_brain")


def build_comparison_xlsx(
    project_id: str,
    insights: dict[str, Any],
    *,
    thread_id: str = "",
    chunks: list[Any] | None = None,
    artifacts: list[Any] | None = None,
) -> dict[str, Any]:
    del chunks, artifacts  # W8: file writer reads SQL, not raw chunks.
    store.write_status(project_id, "xlsx", status="running", thread_id=thread_id or None)
    filename = "comparison_matrix.xlsx"
    path = store.pack_file(project_id, filename)
    source = load_matrix_source(project_id)
    evidence_used = source.warm
    if evidence_used:
        insights = insights_from_source(insights, source)
    process = insights.get("process_type") or ""
    if evidence_used:
        matrix = matrix_from_source(source, process)
    elif process == DIRECT_TG:
        matrix = empty_direct(insights)
    else:
        matrix = empty_indirect(insights)
    wb = Workbook()
    cover = wb.active
    cover.title = "Cover"
    _write_cover(cover, insights, evidence_used=evidence_used)
    _write_vendors(wb.create_sheet("Vendors"), insights)
    if process == DIRECT_TG:
        if not isinstance(matrix, DirectMatrix):
            matrix = empty_direct(insights)
        write_direct(wb, insights, matrix)
    else:
        if not isinstance(matrix, IndirectMatrix):
            matrix = empty_indirect(insights)
        write_indirect(wb, insights, matrix)
    if source.cells:
        _write_citations(wb.create_sheet("Citations"), source)
    if evidence_used or source.pricing_lines:
        _write_pricing(wb.create_sheet("Pricing lines"), source)
    _write_field_map(wb.create_sheet("FieldMap"))
    wb.save(path)
    href = store.flask_href(project_id, "xlsx")
    pack_status = "ready" if evidence_used else "template"
    pack_error = (
        None
        if evidence_used
        else "Template only — no persisted evidence available."
    )
    store.write_status(
        project_id,
        "xlsx",
        status=pack_status,
        href=href,
        filename=filename,
        thread_id=thread_id or None,
        error=pack_error,
    )
    log.info(
        "comparison xlsx {} project_id={} process={} evidence_used={} sheets={}",
        pack_status,
        project_id,
        process or "unset",
        evidence_used,
        wb.sheetnames,
    )
    return {
        "status": pack_status,
        "href": href,
        "filename": filename,
        "path": str(path),
        "llm_used": False,
        "evidence_used": evidence_used,
        "sheets": list(wb.sheetnames),
        "error": pack_error,
    }


def _write_cover(ws, insights: dict[str, Any], *, evidence_used: bool) -> None:
    ws["A1"] = "Mate comparison pack"
    ws["A1"].font = Font(bold=True, size=16, color="FF6900")
    origin = (
        "Cells filled from SQL evidence + pricing_line (no LLM)."
        if evidence_used
        else "Template only — no persisted evidence available."
    )
    ws["A2"] = (
        "Draft workbook. Humans award. Empty is missing, never zero. " + origin
    )
    ws["A4"] = "Named field"
    ws["B4"] = "Value"
    ws["A4"].font = Font(bold=True)
    ws["B4"].font = Font(bold=True)
    for row, (field, key) in enumerate(COVER_FIELDS, start=5):
        ws[f"A{row}"] = field
        ws[f"B{row}"] = insights.get(key, "")
    ws["A12"] = "FIELD_DECISION_SUMMARY"
    ws["B12"] = (insights.get("decision") or {}).get("summary") or ""
    ws["A13"] = "FIELD_WEIGHTS_LOCKED"
    ws["B13"] = "NO — draft scores only"
    ws["A14"] = "FIELD_AWARD"
    ws["B14"] = "Not awarded"
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 72


def _write_vendors(ws, insights: dict[str, Any]) -> None:
    header_row(ws, ["Vendor", "Role", "Files", "Coverage %", "Headline", "Evidence locator"])
    vendors = insights.get("vendors") or []
    if not vendors:
        ws["A2"] = "No vendor column yet"
        return
    for index, vendor in enumerate(vendors, start=2):
        evidence = vendor.get("evidence") or []
        ws[f"A{index}"] = vendor.get("name")
        ws[f"B{index}"] = vendor.get("role")
        ws[f"C{index}"] = vendor.get("artifact_count")
        ws[f"D{index}"] = vendor.get("coverage_pct")
        ws[f"E{index}"] = vendor.get("headline")
        ws[f"F{index}"] = evidence[0].get("locator") if evidence else "missing"
    autosize(ws)


def _write_field_map(ws) -> None:
    header_row(ws, ["PPT field", "Excel sheet", "Cell / column"])
    rows = [
        ("FIELD_PROCESS_LABEL", "Cover", "B6"),
        ("FIELD_OWNER_ENTITY", "Cover", "B7"),
        ("FIELD_PROJECT_CODE", "Cover", "B8"),
        ("FIELD_PROJECT_NAME", "Cover", "B9"),
        ("FIELD_KNOWLEDGE_PCT", "Cover", "B10"),
        ("FIELD_DECISION_SUMMARY", "Cover", "B12"),
        ("FIELD_WEIGHTS_LOCKED", "Cover", "B13"),
        ("FIELD_AWARD", "Cover", "B14"),
        ("FIELD_VENDOR_NAME", "Vendors", "A"),
        ("FIELD_VENDOR_HEADLINE", "Vendors", "E"),
        ("FIELD_TCO", "Final BAFO Comparison", "row Total TCO year 1"),
        ("FIELD_REQUIREMENT_ID", "Procurement Requirements", "A"),
        ("FIELD_CITATION", "Citations", "F"),
        ("FIELD_PRICING_LINE", "Pricing lines", "A"),
    ]
    for index, row in enumerate(rows, start=2):
        ws[f"A{index}"] = row[0]
        ws[f"B{index}"] = row[1]
        ws[f"C{index}"] = row[2]
    autosize(ws)


def _write_pricing(ws, source) -> None:
    header_row(
        ws,
        [
            "Bid",
            "Offer type",
            "Role",
            "Seniority",
            "Rate",
            "Unit",
            "Currency",
            "Quantity",
            "Line total",
            "Etex days",
            "Verified",
            "Artifact",
            "Page",
        ],
    )
    for index, line in enumerate(source.pricing_lines, start=2):
        bid = (line.vendor_id or "").strip()
        ws.cell(index, 1, source.bid_labels.get(bid, bid))
        ws.cell(index, 2, line.offer_type)
        ws.cell(index, 3, line.role or "")
        ws.cell(index, 4, line.seniority or "")
        ws.cell(index, 5, float(line.rate) if line.rate is not None else "")
        ws.cell(index, 6, line.rate_unit or "")
        ws.cell(index, 7, line.currency or "")
        ws.cell(index, 8, float(line.quantity) if line.quantity is not None else "")
        ws.cell(index, 9, float(line.line_total) if line.line_total is not None else "")
        ws.cell(index, 10, float(line.etex_effort_days) if line.etex_effort_days is not None else "")
        ws.cell(index, 11, line.verified)
        names = getattr(source, "artifact_names", {}) or {}
        ws.cell(index, 12, names.get(line.artifact_id or "", line.artifact_id or ""))
        ws.cell(index, 13, line.page if line.page is not None else "")
    autosize(ws)


def _write_citations(ws, source) -> None:
    header_row(
        ws,
        [
            "Requirement",
            "Requirement text",
            "Bid",
            "Status",
            "Claim",
            "Citation",
            "Page",
            "Artifact",
            "Reviewed",
        ],
    )
    req_text = {req.id: req.text for req in source.requirements}
    names = getattr(source, "artifact_names", {}) or {}
    for index, ((req_id, bid), cell) in enumerate(sorted(source.cells.items()), start=2):
        ws.cell(index, 1, req_id)
        ws.cell(index, 2, req_text.get(req_id, ""))
        ws.cell(index, 3, source.bid_labels.get(bid, bid))
        ws.cell(index, 4, cell.status)
        ws.cell(index, 5, (cell.comment or "").split("\n")[-1] if cell.comment else "")
        ws.cell(index, 6, cell.citation or "")
        ws.cell(index, 7, "" if cell.page is None else cell.page)
        ws.cell(index, 8, names.get(cell.artifact_id or "", cell.artifact_id or ""))
        ws.cell(index, 9, "yes" if cell.pinned else "")
    autosize(ws, max_width=48)


def existing_xlsx_path(project_id: str) -> Path | None:
    status = store.read_status(project_id).get("xlsx") or {}
    filename = status.get("filename")
    if not filename:
        return None
    path = store.pack_file(project_id, filename)
    return path if path.exists() else None
