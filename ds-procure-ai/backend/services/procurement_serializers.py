"""Map DB rows to procurement frontend JSON contracts."""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from sqlalchemy.orm import Session

from shared.db.connection import session_scope
from shared.db.models import AppUser, Artifact, Project
from shared.db.repos import artifacts as artifact_repo
from shared.db.repos import projects as project_repo
from services.procurement_data import (
    EMPTY_WORKSPACE_GRAPH,
    STORAGE_LIMIT_BYTES,
    TABS,
)

STATUS_FILTERS = [
    {"value": "all", "label": "All Projects"},
    {"value": "active", "label": "Active"},
    {"value": "on-hold", "label": "On Hold"},
    {"value": "completed", "label": "Completed"},
]


STAGE_LABELS = {
    "no_files": "No files",
    "not_processed": "Not processed",
    "building": "Extracting…",
    "failed": "Extraction failed",
    "staged": "Draft only",
    "needs_review": "Needs review",
    "ready": "Knowledge base ready",
}


def _project_stages(
    project_ids: list[str], *, session: Session | None = None
) -> dict[str, str]:
    """Where each project sits in the pipeline, from two aggregate queries."""
    uploads = artifact_repo.upload_counts(project_ids, session=session)
    # A missing kb_build_job table must not take the whole projects list down.
    try:
        from ai_brain.core.kb.extract import job_store

        kb = job_store.latest_status_map(project_ids, session=session)
    except Exception:
        kb = {}

    stages: dict[str, str] = {}
    for project_id in project_ids:
        run = kb.get(project_id)
        if run in STAGE_LABELS and run != "not_processed":
            stages[project_id] = run
            continue
        stages[project_id] = (
            "not_processed" if uploads.get(project_id, {}).get("total") else "no_files"
        )
    return stages


def nav_payload(user: AppUser | None, identity: dict[str, Any]) -> dict[str, Any]:
    display = _display_name(user, identity)
    return {
        "user": {
            "name": display,
            "role": "AI Workspace",
            "initial": display[:1].upper() if display else "?",
        }
    }


def dashboard_payload(projects: list[Project]) -> dict[str, Any]:
    status_counts = Counter(p.status.lower().replace(" ", "-") for p in projects)
    active = sum(1 for p in projects if p.status.lower() == "active")
    on_hold = sum(1 for p in projects if p.status.lower() == "on hold")
    completed = sum(1 for p in projects if p.status.lower() == "completed")
    total = len(projects)
    total_budget = sum(_parse_budget(p.budget) for p in projects)

    return {
        "kpis": [
            {
                "label": "Total Projects",
                "value": str(total),
                "change": "—",
                "positive": True,
            },
            {
                "label": "Active Projects",
                "value": str(active),
                "change": "—",
                "positive": True,
            },
            {
                "label": "On Hold",
                "value": str(on_hold),
                "change": "—",
                "positive": True,
            },
            {
                "label": "Completed",
                "value": str(completed),
                "change": "—",
                "positive": True,
            },
        ],
        "projectStatus": {
            "total": total,
            "items": _status_items(status_counts),
        },
        "spendByCategory": [],
        "topVendors": [],
        "recentActivity": [],
    }


def projects_page_payload(
    projects: list[Project],
    *,
    total: int,
    page: int,
    page_size: int,
    all_projects: list[Project] | None = None,
) -> dict[str, Any]:
    page = max(page, 1)
    page_size = max(page_size, 1)
    start = (page - 1) * page_size + 1 if total else 0
    end = min(page * page_size, total)
    pages = max((total + page_size - 1) // page_size, 1)

    summary_source = all_projects if all_projects is not None else projects
    rows = [project_repo.project_to_dict(p) for p in projects]
    ids = [row["id"] for row in rows]
    # One connection for all three list aggregates.
    with session_scope() as session:
        coverage = project_repo.mandatory_progress_map(ids, session=session)
        stages = _project_stages(ids, session=session)
    for row in rows:
        stage = stages.get(row["id"], "no_files")
        row["progress"] = coverage.get(row["id"], 0)
        row["stage"] = stage
        row["stageLabel"] = STAGE_LABELS[stage]
        row["building"] = stage == "building"
    return {
        "filters": {
            "status": STATUS_FILTERS,
            "category": _category_filters(summary_source),
        },
        "pagination": {
            "from": start,
            "to": end,
            "total": total,
            "pages": list(range(1, min(pages, 3) + 1)),
            "currentPage": page,
        },
        "projects": rows,
    }


def project_shell_payload(project: Project) -> dict[str, Any]:
    row = project_repo.project_to_dict(project)
    return {
        "project": {
            "id": row["id"],
            "name": row["name"],
            "code": row["code"],
            "status": row["status"],
            "owner": row["owner"],
            "created": row["created"],
            "deadline": row["deadline"],
            "progress": row["progress"],
            "workflowEntryPoint": row["workflowEntryPoint"],
            "businessProcess": row["businessProcess"],
            "requester": row["requester"],
            "dept": row["dept"],
        },
        "tabs": TABS,
    }


def overview_payload(project: Project, artifacts: list[Artifact]) -> dict[str, Any]:
    from ai_brain.core.kb.api.views import build_overview_view

    payload = build_overview_view(project.id, project=project, artifacts=artifacts)
    payload["documents"] = {
        **_document_type_counts(artifacts),
        "recent": [a.original_name for a in artifacts[:3]],
    }
    if not payload.get("requirements") or not payload["requirements"].get("total"):
        fallback = _requirements_summary(project.requirements_json)
        if fallback["total"]:
            payload["requirements"] = fallback
    return payload


def requirements_payload(project_id: str) -> dict[str, Any]:
    from ai_brain.core.kb.api.views import build_requirements_view

    return build_requirements_view(project_id)


def vendors_payload(project_id: str) -> dict[str, Any]:
    from ai_brain.core.kb.api.views import build_vendors_view

    return build_vendors_view(project_id)


def documents_payload(
    artifacts: list[Artifact], packs: dict[str, Any] | None = None
) -> dict[str, Any]:
    groups = _file_groups(artifacts)
    generated = _generated_group(packs)
    if generated:
        groups.append(generated)
    return {"fileGroups": groups}


_PACK_LABELS = {
    "xlsx": ("comparison_matrix.xlsx", "xlsx"),
    "ppt": ("steerco_pack.pptx", "pptx"),
}


def _generated_group(packs: dict[str, Any] | None) -> dict[str, Any] | None:
    """Packs live on the volume, not in `artifact`, so they need their own group."""
    if not packs:
        return None
    files: list[dict[str, Any]] = []
    for kind, (fallback_name, file_type) in _PACK_LABELS.items():
        pack = packs.get(kind) or {}
        href = str(pack.get("href") or "").strip()
        status = str(pack.get("status") or "")
        # `template` is still a real, downloadable file — only idle/failed are not.
        if status not in {"ready", "template"} or not href:
            continue
        updated = str(pack.get("updated_at") or "")[:10]
        label = "Template" if status == "template" else "Generated"
        files.append(
            {
                "id": f"pack-{kind}",
                "name": str(pack.get("filename") or fallback_name),
                "type": file_type,
                "meta": f"{label}{' ' + updated if updated else ''}",
                "href": href,
            }
        )
    if not files:
        return None
    return {"title": artifact_repo.FOLDER_TITLES[artifact_repo.FOLDER_AI_GENERATED], "files": files}


def workspace_payload(
    project: Project,
    artifacts: list[Artifact],
    *,
    user_initial: str,
) -> dict[str, Any]:
    total_bytes = sum(int(a.size_bytes or 0) for a in artifacts)
    percent = min(round((total_bytes / STORAGE_LIMIT_BYTES) * 100), 100) if STORAGE_LIMIT_BYTES else 0
    return {
        "projectName": project.name,
        "files": _workspace_files(artifacts),
        "chatMessages": [],
        "graph": {
            **EMPTY_WORKSPACE_GRAPH,
            "nodes": [{"id": "center", "labelKey": "projectName", "className": "center"}],
        },
        "storage": {
            "label": f"{_format_storage(total_bytes)} of 10 GB",
            "percent": percent,
        },
        "userInitial": user_initial,
    }


def chat_project_dict(project: Project) -> dict[str, Any]:
    row = project_repo.project_to_dict(project)
    return {
        "id": row["id"],
        "name": row["name"],
        "code": row["code"],
        "status": row["status"],
        "owner": row["owner"],
        "workflowEntryPoint": row["workflowEntryPoint"],
        "businessProcess": row["businessProcess"],
        "category": row["category"],
        "region": row["region"],
        "requester": row["requester"],
        "dept": row["dept"],
        "description": row["description"],
        "awardHorizon": row["awardHorizon"],
        "targetSpend": row.get("budget") or "",
    }


def _display_name(user: AppUser | None, identity: dict[str, Any]) -> str:
    if user is not None:
        return user.display_name or user.user_name or user.email or "User"
    session_user = identity.get("user") if isinstance(identity, dict) else None
    if isinstance(session_user, dict):
        return (
            session_user.get("display_name")
            or session_user.get("user_name")
            or session_user.get("email")
            or "User"
        )
    return "User"


def _status_items(status_counts: Counter) -> list[dict[str, Any]]:
    mapping = [
        ("active", "Active"),
        ("evaluation", "Evaluation"),
        ("negotiation", "Negotiation"),
        ("decision-pending", "Decision Pending"),
        ("completed", "Completed"),
    ]
    items = []
    for key, label in mapping:
        count = status_counts.get(key, 0)
        if count:
            items.append({"label": label, "count": count, "dot": key})
    return items


def _category_filters(projects: list[Project]) -> list[dict[str, str]]:
    categories = sorted({p.category for p in projects if p.category})
    options = [{"value": "all", "label": "All Categories"}]
    for category in categories:
        slug = re.sub(r"[^a-z0-9]+", "-", category.lower()).strip("-") or "other"
        options.append({"value": slug, "label": category})
    return options


def _requirements_summary(requirements_json: str | None) -> dict[str, int]:
    if not requirements_json:
        return {"total": 0, "approved": 0, "pending": 0, "rejected": 0}
    try:
        rows = json.loads(requirements_json)
    except json.JSONDecodeError:
        return {"total": 0, "approved": 0, "pending": 0, "rejected": 0}
    if not isinstance(rows, list):
        return {"total": 0, "approved": 0, "pending": 0, "rejected": 0}
    return {
        "total": len(rows),
        "approved": 0,
        "pending": len(rows),
        "rejected": 0,
    }


def _document_type_counts(artifacts: list[Artifact]) -> dict[str, int]:
    counts = Counter(artifact_repo.artifact_file_type(a.original_name) for a in artifacts)
    return {
        "pdf": counts.get("pdf", 0),
        "docx": counts.get("docx", 0),
        "xlsx": counts.get("xlsx", 0),
    }


def _current_only(artifacts: list[Artifact]) -> list[Artifact]:
    """Retired revisions stay in the table for audit but must not be listed twice."""
    return [a for a in artifacts if not getattr(a, "superseded_by", None)]


def _file_groups(artifacts: list[Artifact]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for artifact in _current_only(artifacts):
        folder = artifact.folder or artifact_repo.FOLDER_VENDOR
        grouped.setdefault(folder, []).append(
            {
                "id": artifact.id,
                "name": artifact.original_name,
                "type": artifact_repo.artifact_file_type(artifact.original_name),
                "meta": artifact_repo.format_file_meta(artifact.size_bytes, artifact.created_at),
            }
        )

    groups = []
    for folder, title in artifact_repo.FOLDER_TITLES.items():
        files = grouped.get(folder, [])
        if files:
            groups.append({"title": title, "files": files})
    return groups


def _vendor_label(vendor_id: str | None) -> str:
    slug = (vendor_id or "").strip()
    if not slug:
        return "Others"
    # Short slugs are acronyms (ey, pwc); longer ones are already readable.
    return slug.upper() if len(slug) <= 3 else slug


def _vendor_subgroups(artifacts: list[Artifact]) -> list[dict[str, Any]]:
    """Vendor folder split by bid so the tree mirrors how extraction sees the files."""
    buckets: dict[str, list[str]] = {}
    for artifact in artifacts:
        if not artifact.original_name:
            continue
        buckets.setdefault(_vendor_label(artifact.vendor_id), []).append(
            artifact.original_name
        )
    named = sorted((k for k in buckets if k != "Others"), key=str.lower)
    ordered = named + (["Others"] if "Others" in buckets else [])
    return [{"label": label, "files": buckets[label]} for label in ordered]


def _workspace_files(artifacts: list[Artifact]) -> dict[str, Any]:
    artifacts = _current_only(artifacts)
    inputs: list[dict[str, Any]] = []
    generated: list[str] = []
    for folder, title in artifact_repo.FOLDER_TITLES.items():
        in_folder = [
            a for a in artifacts if (a.folder or artifact_repo.FOLDER_VENDOR) == folder
        ]
        names = [a.original_name for a in in_folder]
        if folder == artifact_repo.FOLDER_AI_GENERATED:
            generated = names
        elif names:
            entry: dict[str, Any] = {"folder": title, "files": names}
            if folder == artifact_repo.FOLDER_VENDOR:
                entry["groups"] = _vendor_subgroups(in_folder)
            inputs.append(entry)

    upload_count = sum(
        1 for a in artifacts if a.kind == "upload"
    )
    return {
        "inputs": inputs,
        "generated": generated,
        "artifacts": [],
        "inputsCount": upload_count,
        "statuses": {
            a.original_name: a.parse_status or "pending"
            for a in artifacts
            if a.original_name
        },
    }


def _parse_budget(value: str | None) -> float:
    if not value:
        return 0.0
    digits = re.sub(r"[^0-9.]", "", value)
    try:
        return float(digits)
    except ValueError:
        return 0.0


def _format_currency(amount: float) -> str:
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"${amount:,.0f}"
    return f"${amount:,.2f}"


def _format_storage(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes} B"
