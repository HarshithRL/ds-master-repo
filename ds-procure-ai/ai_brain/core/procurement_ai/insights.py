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
from shared.logger_global import get_logger

log = get_logger(__name__, service="ai_brain")

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
    requirements = _requirement_card(process_type, artifacts, chunks or [])
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
        "stale": _staleness(artifacts, packs),
    }
    try:
        from ai_brain.core.procurement_ai.packs.matrix_from_evidence import (
            insights_from_source,
            load_matrix_source,
        )

        source = load_matrix_source(getattr(project, "id", ""))
        if source.warm:
            payload = insights_from_source(payload, source)
    except Exception as exc:
        log.warning("insights_from_source failed project_id={}: {}", getattr(project, "id", ""), exc)
    return payload


def _staleness(artifacts: list[Any], packs: dict[str, Any]) -> dict[str, Any]:
    """Flag outputs that no longer describe the inputs.

    Timestamps are ISO-8601 UTC, so string order is chronological order.
    """
    kb_at = str((packs.get("kb") or {}).get("updated_at") or "")
    xlsx_at = str((packs.get("xlsx") or {}).get("updated_at") or "")
    kb_ready = str((packs.get("kb") or {}).get("status") or "") == "ready"
    xlsx_written = str((packs.get("xlsx") or {}).get("status") or "") in {"ready", "template"}

    new_files = 0
    new_notes = 0
    if kb_at:
        for item in artifacts:
            if str(getattr(item, "created_at", "") or "") <= kb_at:
                continue
            if (getattr(item, "kind", "") or "") == "note":
                new_notes += 1
            else:
                new_files += 1

    kb_stale = bool(kb_ready and (new_files or new_notes))
    # A rebuilt knowledge base makes the workbook describe the previous one.
    xlsx_stale = bool(xlsx_written and (kb_stale or (kb_at and xlsx_at and kb_at > xlsx_at)))
    return {
        "kb": kb_stale,
        "kb_new_files": new_files,
        "kb_new_notes": new_notes,
        "xlsx": xlsx_stale,
    }


def _kb_status(project_id: str, file_count: int, packs: dict[str, Any]) -> tuple[str, str | None]:
    job = packs.get("kb") if isinstance(packs.get("kb"), dict) else {}
    job_status = str(job.get("status") or "").strip()
    job_message = job.get("message")
    if job_status in {"ingesting", "building"}:
        # A build whose worker stopped reporting is dead, not slow. Surface it
        # instead of leaving the UI spinning indefinitely.
        reaped = _reaped_kb_status(project_id, file_count)
        if reaped is not None:
            return reaped
    if job_status in {"ingesting", "building", "failed", "ready", "needs_review", "staged"}:
        return job_status, job_message or _default_kb_message(job_status, file_count)
    if not file_count:
        return "empty", None
    try:
        from ai_brain.core.kb.store.persist import kb_counts

        counts = kb_counts(project_id) if project_id else {}
    except Exception as exc:
        log.warning("kb_counts failed project_id={}: {}", project_id, exc)
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


def _reaped_kb_status(project_id: str, file_count: int) -> tuple[str, str | None] | None:
    """Flip a stalled build to failed. Returns None when the run is still alive."""
    if not project_id:
        return None
    try:
        from ai_brain.core.kb.extract import job_store

        reaped = job_store.reap_stalled(project_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("kb stall check failed project_id={}: {}", project_id, exc)
        return None
    if not reaped:
        return None
    return "failed", reaped.get("message") or _default_kb_message("failed", file_count)


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


# Checklist keys the LLM classifier already answers authoritatively via doc_role.
_ROLE_FOR_KEY = {
    "proposal": ("proposal",),
    "pricing_days": ("pricing",),
    "pricing_tco": ("pricing",),
    "pricing_pq": ("pricing",),
    "references": ("reference",),
}

# Whole-word phrases searched in parsed document text. Filename matching used to
# decide these, which both passed "Vendor proposal" off the RFP's own filename
# and missed priced proposals whose names contain no commercial word.
_CONTENT_PHRASES = {
    "nda": ("non-disclosure", "nondisclosure", "confidentiality agreement", "nda"),
    "dpa": ("data processing agreement", "gdpr", "data protection agreement"),
    "proposal": ("our proposal", "we propose", "statement of work"),
    "pricing_days": ("day rate", "daily rate", "man-day", "manday", "blended rate"),
    "pricing_tco": ("tco", "total cost of ownership", "licence fee", "license fee"),
    "pricing_pq": ("unit price", "quantity", "price per"),
    "technical": ("technical specification", "test report", "laboratory"),
    "safety": ("safety data", "fire rating", "reach regulation"),
    "architecture": ("architecture", "solution design", "integration design"),
    "evsat": ("evsat", "security assessment", "penetration test"),
    "requirements": ("requirements matrix", "specification", "scope of work"),
    "references": ("reference client", "case study", "referenceable"),
}


def _phrase_present(phrase: str, blob: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", blob) is not None


def _content_blob(chunks: list[Any]) -> str:
    parts: list[str] = []
    total = 0
    for chunk in chunks or []:
        text = (getattr(chunk, "text", "") or "").lower()
        if not text:
            continue
        parts.append(text)
        total += len(text)
        if total > 2_000_000:
            break
    return "\n".join(parts)


def _requirement_card(
    process_type: str, artifacts: list[Any], chunks: list[Any] | None = None
) -> dict[str, Any]:
    roles = {
        (getattr(a, "doc_role", "") or "").strip().lower()
        for a in artifacts
        if (getattr(a, "doc_role", "") or "").strip()
    }
    blob = _content_blob(chunks or [])
    items = []
    for spec in checklist_for(process_type):
        key = spec["checklist_key"]
        met = any(role in roles for role in _ROLE_FOR_KEY.get(key, ()))
        if not met and blob:
            met = any(
                _phrase_present(phrase, blob) for phrase in _CONTENT_PHRASES.get(key, ())
            )
        items.append(
            {
                **spec,
                "status": "met" if met else "missing",
                "needed": None if met else f"Upload {spec['label']} or mark N/A",
            }
        )
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
