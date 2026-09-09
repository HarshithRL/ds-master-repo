"""Build Studio insight cards from project files. No LLM. Cite or say missing."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ai_brain.core.procurement_ai.packs import store as pack_store
from ai_brain.core.procurement_ai.process_type import (
    checklist_for,
    classify_process_type,
    owner_label,
    process_chip,
)

KNOWN_VENDORS = (
    "EY", "BDO", "KPMG", "PwC", "PWC", "Trifinance", "Inetum", "HISENER",
    "Sphera", "SAP", "Tagetik", "Kyriba", "ION", "FIS",
)


def _pack_card(row: Any, status: str) -> dict[str, Any]:
    pack = row if isinstance(row, dict) else {}
    return {
        "status": status,
        "href": pack.get("href"),
        "thread_id": pack.get("thread_id"),
        "error": pack.get("error"),
    }


_KEY_HINTS = {
    "nda": ("nda", "non-disclosure"),
    "dpa": ("dpa", "gdpr", "data processing"),
    "proposal": ("proposal", "offer", "response", "rfp"),
    "pricing_days": ("pric", "day", "rate", "fee", "commercial"),
    "pricing_tco": ("pric", "tco", "licence", "license", "commercial"),
    "pricing_pq": ("pric", "quote", "pq", "p*q", "commercial"),
    "technical": ("technical", "lab", "spec"),
    "safety": ("safety", "fire", "reach"),
    "architecture": ("architecture", "solution design", "integration"),
    "evsat": ("evsat", "security assessment"),
    "requirements": ("requirement", "specification", "rfx"),
    "references": ("reference", "case study"),
}


def build_insight_payload(project: Any, artifacts: list[Any], chunks: list[Any] | None = None) -> dict[str, Any]:
    file_blob = " ".join(getattr(a, "original_name", "") or "" for a in artifacts)
    process_type = classify_process_type(
        business_process=getattr(project, "business_process", None),
        category=getattr(project, "category", None),
        name=getattr(project, "name", None),
        description=" ".join(
            part for part in (getattr(project, "description", None), file_blob) if part
        ),
    )
    vendors = _vendor_cards(artifacts, chunks or [])
    requirements = _requirement_card(process_type, artifacts)
    packs = pack_store.pack_status(getattr(project, "id", ""))
    parsed_ok = sum(1 for a in artifacts if (getattr(a, "parse_status", "") or "") == "ok")
    file_count = len(artifacts)
    kb_status, kb_message = _kb_status(getattr(project, "id", ""), file_count, packs)
    mandatory = [item for item in requirements["items"] if item["severity"] == "blocking"]
    mandatory_met = sum(1 for item in mandatory if item["status"] == "met")
    knowledge_pct = int(round((mandatory_met / len(mandatory)) * 100)) if mandatory else 0
    blockers: list[str] = []
    if not process_type:
        blockers.append("Process type unset — classify Direct TG vs IT")
    if file_count == 0:
        blockers.append("No files uploaded")
    for item in mandatory:
        if item["status"] == "missing":
            blockers.append(f"Missing {item['label']}")
    can_build_xlsx = bool(process_type and file_count)
    can_build_ppt = packs.get("xlsx", {}).get("status") == "ready"
    xlsx_status = packs.get("xlsx", {}).get("status") or ("idle" if can_build_xlsx else "blocked")
    ppt_status = packs.get("ppt", {}).get("status") or ("idle" if can_build_ppt else "blocked")
    if not can_build_xlsx and xlsx_status == "idle":
        xlsx_status = "blocked"
    if not can_build_ppt and ppt_status == "idle":
        ppt_status = "blocked"
    payload = {
        "project_id": getattr(project, "id", ""),
        "project_code": getattr(project, "code", ""),
        "project_name": getattr(project, "name", ""),
        "process_type": process_type,
        "process_label": process_chip(process_type),
        "owner_entity": owner_label(process_type),
        "kb_status": kb_status,
        "kb_message": kb_message,
        "kb_version": 1,
        "knowledge_pct": knowledge_pct,
        "file_count": file_count,
        "parsed_ok": parsed_ok,
        "vendors": vendors,
        "requirements": requirements,
        "decision": {
            "can_publish_kb": bool(file_count and process_type),
            "can_build_xlsx": can_build_xlsx,
            "can_build_ppt": can_build_ppt,
            "blockers": blockers,
            "stage": "rfp_in",
            "weights_locked": False,
            "summary": _decision_summary(process_type, knowledge_pct, can_build_xlsx, can_build_ppt, blockers),
        },
        "packs": {
            "xlsx": _pack_card(packs.get("xlsx"), xlsx_status),
            "ppt": _pack_card(packs.get("ppt"), ppt_status),
        },
    }
    try:
        from ai_brain.core.procurement_ai.packs.matrix_from_evidence import (
            insights_from_source,
            load_matrix_source,
        )

        source = load_matrix_source(getattr(project, "id", ""))
        if source.warm:
            payload = insights_from_source(payload, source)
    except Exception:
        pass
    return payload


def _kb_status(project_id: str, file_count: int, packs: dict[str, Any]) -> tuple[str, str | None]:
    job = packs.get("kb") if isinstance(packs.get("kb"), dict) else {}
    job_status = str(job.get("status") or "").strip()
    job_message = job.get("message")
    if job_status in {"ingesting", "building", "failed", "ready", "needs_review", "staged"}:
        return job_status, job_message or _default_kb_message(job_status, file_count)
    if not file_count:
        return "empty", None
    try:
        from ai_brain.core.kb.store.persist import kb_counts

        counts = kb_counts(project_id) if project_id else {}
    except Exception:
        counts = {}
    evidence = int(counts.get("evidence") or 0)
    classified = int(counts.get("classified") or 0)
    if evidence:
        if packs.get("xlsx", {}).get("status") == "ready":
            return "ready", _default_kb_message("ready", file_count)
        return "building", _default_kb_message("building", file_count)
    if classified:
        return "building", _default_kb_message("building", file_count)
    return "ingesting", _default_kb_message("ingesting", file_count)


def _default_kb_message(status: str, file_count: int) -> str:
    if status == "ingesting":
        return "Parsing uploaded files…"
    if status == "building":
        return "Building knowledge base — extracting vendor evidence…"
    if status == "staged":
        return "Files uploaded. Waiting to extract bids…"
    if status == "failed":
        return "Knowledge base build failed."
    if status == "needs_review":
        return "Knowledge base needs review."
    if status == "ready":
        noun = "file" if file_count == 1 else "files"
        return f"Knowledge base ready · {file_count} {noun}."
    return "Knowledge base updating…"


def _decision_summary(process_type: str, knowledge_pct: int, can_xlsx: bool, can_ppt: bool, blockers: list[str]) -> str:
    if not process_type:
        return "Classify the process before comparison. Do not mix Direct TG and Indirect IT."
    if can_ppt:
        return "Comparison Excel is ready. Build SteerCo from named Excel fields when you want the pack."
    if can_xlsx:
        return f"Draft comparison can be built from uploaded files ({knowledge_pct}% mandatory coverage). Scores stay draft until weights are locked. Humans award."
    return blockers[0] if blockers else "Files or process type missing"


def _vendor_cards(artifacts: list[Any], chunks: list[Any]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Any]] = {}
    for artifact in artifacts:
        name = _vendor_name(getattr(artifact, "original_name", "") or "")
        if not name:
            continue
        grouped.setdefault(name, []).append(artifact)
    cards = []
    chunks_by_artifact = _chunks_by_artifact(chunks)
    for index, (name, files) in enumerate(grouped.items(), start=1):
        evidence = []
        for artifact in files:
            for chunk in chunks_by_artifact.get(getattr(artifact, "id", ""), [])[:1]:
                quote = (getattr(chunk, "text", "") or "").strip().replace("\n", " ")
                evidence.append({"chunk_id": getattr(chunk, "id", ""), "locator": _locator(chunk), "quote": quote[:180]})
        cards.append({
            "vendor_id": f"v-{index}",
            "name": name,
            "role": "bidder",
            "artifact_count": len(files),
            "roles_seen": _roles_seen(files),
            "fact_count": len(evidence),
            "blocking_gaps": 0,
            "coverage_pct": min(100, len(files) * 25),
            "headline": f"{len(files)} file(s) on record.",
            "evidence": evidence[:3],
        })
    return cards


def _vendor_name(filename: str) -> str | None:
    stem = Path(filename).stem
    blob = re.sub(r"[_\-]+", " ", stem)
    upper = blob.upper()
    lower = blob.lower()
    if "rfp" in lower and not any(known.upper() in upper for known in KNOWN_VENDORS):
        return None
    if "TRIFINANCE" in upper or "INETUM" in upper:
        return "TriFinance + Inetum"
    for known in KNOWN_VENDORS:
        if re.search(rf"\b{re.escape(known.upper())}\b", upper):
            return "PwC" if known.upper() == "PWC" else known
    if "INDEPENDENT ASSESSMENT" in upper and "SWIFT" in upper:
        return "BDO"
    return blob.strip()[:48] or "Unnamed vendor"


def _roles_seen(files: list[Any]) -> list[str]:
    roles = []
    for artifact in files:
        name = (getattr(artifact, "original_name", "") or "").lower()
        if "nda" in name:
            roles.append("nda")
        elif "pric" in name or "commercial" in name:
            roles.append("price")
        elif "proposal" in name or "offer" in name:
            roles.append("proposal")
        else:
            roles.append("document")
    return list(dict.fromkeys(roles))


def _requirement_card(process_type: str, artifacts: list[Any]) -> dict[str, Any]:
    names = " ".join((getattr(a, "original_name", "") or "").lower() for a in artifacts)
    items = []
    for spec in checklist_for(process_type):
        hints = _KEY_HINTS.get(spec["checklist_key"], (spec["checklist_key"],))
        met = any(hint in names for hint in hints)
        items.append({**spec, "status": "met" if met else "missing", "needed": None if met else f"Upload {spec['label']} or mark N/A"})
    mandatory = [i for i in items if i["severity"] == "blocking"]
    return {
        "mandatory_total": len(mandatory),
        "mandatory_met": sum(1 for i in mandatory if i["status"] == "met"),
        "mandatory_partial": 0,
        "mandatory_missing": sum(1 for i in mandatory if i["status"] == "missing"),
        "items": items,
    }


def _chunks_by_artifact(chunks: list[Any]) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = {}
    for chunk in chunks:
        grouped.setdefault(getattr(chunk, "artifact_id", ""), []).append(chunk)
    return grouped


def _locator(chunk: Any) -> str:
    raw = getattr(chunk, "location_json", None)
    if not raw:
        return f"chunk {getattr(chunk, 'ordinal', 0)}"
    try:
        loc = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except json.JSONDecodeError:
        return f"chunk {getattr(chunk, 'ordinal', 0)}"
    page = loc.get("page") or loc.get("slide") or loc.get("sheet")
    if page is not None:
        return f"p.{page}" if "page" in loc else str(page)
    return loc.get("locator") or f"chunk {getattr(chunk, 'ordinal', 0)}"
