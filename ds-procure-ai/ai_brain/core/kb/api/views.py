"""Assemble Overview / Requirements / Vendors payloads from SQL MatrixSource.

No LLM. Graph fill_* nodes write packs/views/*.json; Flask APIs call the same
builders live so tabs still fill if a view file is missing.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ai_brain.core.procurement_ai.packs import store as pack_store
from ai_brain.core.procurement_ai.packs.matrix_from_evidence import (
    MatrixSource,
    load_matrix_source,
)
from ai_brain.core.procurement_ai.project_context import load_artifacts, load_project
from shared.db.repos import artifacts as artifact_repo

COVERED_STATUSES = frozenset({"met", "partial"})
TIMELINE_IDS = frozenset({f"R{i:02d}" for i in range(10, 18)})
QUICK_ACTIONS = [
    "Add Requirement",
    "Invite Vendor",
    "Compare Vendors",
    "AI Risk Assessment",
    "Generate Report",
]
RESPONDED_KEYS = ("y1_tco", "tco_3_5", "timeline")


def _kb_meta(project_id: str) -> dict[str, Any]:
    packs = pack_store.read_status(project_id) if project_id else {}
    kb = packs.get("kb") if isinstance(packs.get("kb"), dict) else {}
    return {
        "kb_status": str(kb.get("status") or "idle"),
        "kb_message": kb.get("message"),
    }


def _coverage_chip(statuses: list[str]) -> str:
    if "met" in statuses:
        return "met"
    if "partial" in statuses:
        return "partial"
    return "gap"


def _req_statuses(source: MatrixSource, req_id: str) -> list[str]:
    out: list[str] = []
    for bid in source.bids:
        cell = source.cells.get((req_id, bid))
        if cell is not None and (cell.status or "").strip():
            out.append(cell.status)
    return out


def _mandatory_progress(source: MatrixSource) -> int:
    mandatory = [row for row in source.requirements if int(row.mandatory or 0)]
    if not mandatory:
        return 0
    covered = 0
    for row in mandatory:
        statuses = _req_statuses(source, row.id)
        if COVERED_STATUSES.intersection(statuses):
            covered += 1
    return int(round((covered / len(mandatory)) * 100))


def _bid_responded(source: MatrixSource, bid: str) -> bool:
    if any(key[1] == bid for key in source.cells):
        return True
    if any((line.vendor_id or "").strip() == bid for line in source.pricing_lines):
        return True
    profile = source.profiles.get(bid) or {}
    return any(str(profile.get(key) or "").strip() for key in RESPONDED_KEYS)


def _profile_text(profile: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(profile.get(key) or "").strip()
        if value and value.lower() != "missing":
            return value
    return ""


def _budget_value(project: Any, source: MatrixSource) -> str:
    project_budget = str(getattr(project, "budget", None) or "").strip()
    if project_budget:
        return project_budget
    for bid in source.bids:
        tco = _profile_text(source.profiles.get(bid) or {}, "y1_tco", "tco_3_5")
        if tco:
            return tco
    totals: list[str] = []
    for line in source.pricing_lines:
        total = line.line_total
        if total is None:
            continue
        currency = (line.currency or "").strip()
        text = f"{total} {currency}".strip() if currency else str(total)
        if text:
            totals.append(text)
    if len(totals) == 1:
        return totals[0]
    if totals:
        return f"{len(totals)} pricing lines"
    return "—"


def _document_counts(artifacts: list[Any]) -> dict[str, Any]:
    from collections import Counter

    counts = Counter(artifact_repo.artifact_file_type(a.original_name) for a in artifacts)
    return {
        "pdf": counts.get("pdf", 0),
        "docx": counts.get("docx", 0),
        "xlsx": counts.get("xlsx", 0),
        "recent": [a.original_name for a in artifacts[:3]],
    }


def _milestones(source: MatrixSource) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for bid in source.bids:
        timeline = _profile_text(source.profiles.get(bid) or {}, "timeline")
        if not timeline:
            continue
        label = source.bid_labels.get(bid, bid)
        items.append(
            {
                "title": f"{label} timeline",
                "date": timeline,
                "status": "Extracted",
            }
        )
    for row in source.requirements:
        if row.id not in TIMELINE_IDS:
            continue
        statuses = _req_statuses(source, row.id)
        if COVERED_STATUSES.intersection(statuses):
            status = "On track"
        elif statuses:
            status = "At risk"
        else:
            status = "Upcoming"
        items.append(
            {
                "title": row.text,
                "date": row.section or "",
                "status": status,
            }
        )
    return items


def _insights(source: MatrixSource, kb_audit: dict[str, Any] | None, kb_status: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    summary = str(source.summary or "").strip()
    if summary:
        items.append({"title": "Extraction summary", "body": summary, "type": "info"})
    audit = kb_audit if isinstance(kb_audit, dict) else {}
    failed = int(audit.get("failed") or 0)
    bundles = int(audit.get("bundle_count") or 0)
    if failed:
        items.append(
            {
                "title": "Bids needing review",
                "body": f"{failed} of {bundles} bid(s) failed extraction.",
                "type": "warning",
            }
        )
    if source.pricing_lines:
        items.append(
            {
                "title": "Pricing found",
                "body": f"{len(source.pricing_lines)} pricing line(s) persisted from vendor files.",
                "type": "info",
            }
        )
    if source.profiles:
        items.append(
            {
                "title": "BAFO profiles",
                "body": f"{len(source.profiles)} vendor profile(s) with timeline / TCO facts.",
                "type": "info",
            }
        )
    if source.flags:
        items.append(
            {
                "title": "Quality flags",
                "body": "; ".join(source.flags[:4]),
                "type": "warning",
            }
        )
    if not items and kb_status in {"ingesting", "building", "staged", "extracting"}:
        items.append(
            {
                "title": "Knowledge extraction",
                "body": "Building the knowledge base from uploaded files.",
                "type": "info",
            }
        )
    return items[:4]


def _stages(file_count: int, kb_status: str, source: MatrixSource) -> list[dict[str, Any]]:
    building = kb_status in {"ingesting", "building", "staged", "extracting"}
    ready = kb_status in {"ready", "needs_review"}
    return [
        {
            "name": "Files uploaded",
            "done": file_count > 0,
            "current": file_count == 0,
        },
        {
            "name": "Knowledge extraction",
            "done": ready,
            "current": building,
        },
        {
            "name": "Evaluation",
            "done": False,
            "current": ready and source.warm,
        },
    ]


def _requirement_counts(source: MatrixSource) -> dict[str, int]:
    total = len(source.requirements)
    pending = sum(1 for row in source.requirements if not _req_statuses(source, row.id))
    return {
        "total": total,
        "approved": 0,
        "pending": pending,
        "rejected": 0,
    }


def _vendor_counts(source: MatrixSource) -> dict[str, int]:
    invited = len(source.bids)
    responded = sum(1 for bid in source.bids if _bid_responded(source, bid))
    return {"invited": invited, "responded": responded, "shortlisted": 0}


def _bid_coverage_pct(source: MatrixSource, bid: str) -> int:
    mandatory = [row for row in source.requirements if int(row.mandatory or 0)]
    if not mandatory:
        return 0
    covered = 0
    for row in mandatory:
        cell = source.cells.get((row.id, bid))
        if cell is not None and cell.status in COVERED_STATUSES:
            covered += 1
    return int(round((covered / len(mandatory)) * 100))


def build_overview_view(
    project_id: str,
    *,
    project: Any | None = None,
    artifacts: list[Any] | None = None,
    kb_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pid = str(project_id or "").strip()
    meta = _kb_meta(pid)
    source = load_matrix_source(pid) if pid else load_matrix_source("")
    if project is None and pid:
        project = load_project(pid)
    if artifacts is None and pid:
        artifacts = load_artifacts(pid)
    artifacts = artifacts or []
    progress = _mandatory_progress(source)
    return {
        **meta,
        "project": {
            "code": getattr(project, "code", "") or "",
            "progress": progress,
        },
        "stages": _stages(len(artifacts), meta["kb_status"], source),
        "metrics": [{"label": "Budget", "value": _budget_value(project, source)}],
        "milestones": _milestones(source),
        "insights": _insights(source, kb_audit, meta["kb_status"]),
        "requirements": _requirement_counts(source),
        "vendors": _vendor_counts(source),
        "documents": _document_counts(artifacts),
        "approvals": [],
        "quickActions": list(QUICK_ACTIONS),
    }


def build_requirements_view(project_id: str) -> dict[str, Any]:
    pid = str(project_id or "").strip()
    meta = _kb_meta(pid)
    source = load_matrix_source(pid) if pid else load_matrix_source("")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in source.requirements:
        statuses = _req_statuses(source, row.id)
        grouped[row.category or "other"].append(
            {
                "id": row.id,
                "text": row.text,
                "section": row.section or "",
                "category": row.category or "other",
                "mandatory": bool(int(row.mandatory or 0)),
                "coverage": _coverage_chip(statuses),
                "bid_statuses": {
                    source.bid_labels.get(bid, bid): (
                        source.cells[(row.id, bid)].status
                        if (row.id, bid) in source.cells
                        else "not_stated"
                    )
                    for bid in source.bids
                },
            }
        )
    groups = [
        {"category": category, "items": items}
        for category, items in grouped.items()
    ]
    return {
        **meta,
        "total": len(source.requirements),
        "groups": groups,
        "items": [item for group in groups for item in group["items"]],
    }


def build_vendors_view(project_id: str) -> dict[str, Any]:
    pid = str(project_id or "").strip()
    meta = _kb_meta(pid)
    source = load_matrix_source(pid) if pid else load_matrix_source("")
    vendors: list[dict[str, Any]] = []
    for bid in source.bids:
        profile = source.profiles.get(bid) or {}
        files = list(source.sources_by_bid.get(bid) or [])
        tco = _profile_text(profile, "y1_tco", "tco_3_5")
        vendors.append(
            {
                "bid_id": bid,
                "name": source.bid_labels.get(bid, bid),
                "legal_name": source.legal_names.get(bid) or _profile_text(profile, "legal_name") or bid,
                "files": files,
                "file_count": len(files),
                "coverage_pct": _bid_coverage_pct(source, bid),
                "responded": _bid_responded(source, bid),
                "tco": tco,
                "timeline": _profile_text(profile, "timeline"),
                "ecovadis": _profile_text(profile, "ecovadis"),
                "delivery_model": _profile_text(profile, "delivery_model"),
                "headline": tco or _profile_text(profile, "y1_solution") or "; ".join(files),
            }
        )
    return {
        **meta,
        "total": len(vendors),
        "vendors": vendors,
    }


def write_view(project_id: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    return pack_store.write_view(project_id, kind, payload)
