"""Map DB rows to procurement frontend JSON contracts."""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

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
    status_counts = Counter(p.status.lower() for p in summary_source)
    return {
        "summary": [
            {"label": "Total Projects", "value": str(total), "trend": "—"},
            {"label": "Active Projects", "value": str(status_counts.get("active", 0)), "trend": "—"},
            {"label": "On Hold", "value": str(status_counts.get("on hold", 0)), "trend": "—"},
            {"label": "Completed", "value": str(status_counts.get("completed", 0)), "trend": "—"},
        ],
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
        "projects": [project_repo.project_to_dict(p) for p in projects],
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


def documents_payload(artifacts: list[Artifact]) -> dict[str, Any]:
    return {"fileGroups": _file_groups(artifacts)}


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


def _file_groups(artifacts: list[Artifact]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for artifact in artifacts:
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


def _workspace_files(artifacts: list[Artifact]) -> dict[str, Any]:
    inputs: list[dict[str, Any]] = []
    generated: list[str] = []
    for folder, title in artifact_repo.FOLDER_TITLES.items():
        names = [
            a.original_name
            for a in artifacts
            if (a.folder or artifact_repo.FOLDER_VENDOR) == folder
        ]
        if folder == artifact_repo.FOLDER_AI_GENERATED:
            generated = names
        elif names:
            inputs.append({"folder": title, "files": names})

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
