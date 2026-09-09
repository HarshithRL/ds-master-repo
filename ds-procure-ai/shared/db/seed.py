"""Idempotent seed data for hub modules."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.db.models import HubModule

HUB_MODULES: list[dict[str, str | int]] = [
    {
        "id": "procurement-ai-assistant",
        "name": "Procurement AI Assistant",
        "description": (
            "Ask questions, generate insights, and receive AI-powered support "
            "to enhance your work."
        ),
        "icon": "/assets/icon-chat.svg",
        "path": "/app/procurement-ai-assistant",
        "category": "General",
        "sort_order": 1,
        "enabled": 1,
    },
    {
        "id": "document-builder",
        "name": "Document Builder",
        "description": (
            "Create, merge and edit documents or code instantly with AI-driven precision."
        ),
        "icon": "/assets/icon-document.svg",
        "path": "/app/document-builder",
        "category": "General",
        "sort_order": 2,
        "enabled": 0,
    },
    {
        "id": "document-translator",
        "name": "Document Translator",
        "description": "Translate texts and document files while preserving the format.",
        "icon": "/assets/icon-translate.svg",
        "path": "/app/document-translator",
        "category": "General",
        "sort_order": 3,
        "enabled": 0,
    },
    {
        "id": "scope-builder",
        "name": "Scope Builder",
        "description": "Transform raw requirements into actionable user stories.",
        "icon": "/assets/icon-scope.svg",
        "path": "/app/scope-builder",
        "category": "General",
        "sort_order": 4,
        "enabled": 0,
    },
    {
        "id": "accounting",
        "name": "Accounting Assistant",
        "description": "Ask questions and find answers from the Group Accounting Manual.",
        "icon": "/assets/icon-accounting.svg",
        "path": "/app/accounting",
        "category": "Group Accounting Manual",
        "sort_order": 5,
        "enabled": 0,
    },
    {
        "id": "policy-search",
        "name": "Policy Search",
        "description": "Search accounting policies and guidelines using AI.",
        "icon": "/assets/icon-search.svg",
        "path": "/app/policy-search",
        "category": "Group Accounting Manual",
        "sort_order": 6,
        "enabled": 0,
    },
]

PROCUREMENT_MODULE_ID = "procurement-ai-assistant"


def _module_id_from_path(path: str) -> str:
    slug = path.rstrip("/").split("/")[-1]
    return slug


def seed_hub_modules(session: Session) -> None:
    for row in HUB_MODULES:
        module_id = str(row["id"])
        existing = session.get(HubModule, module_id)
        if existing is None:
            session.add(
                HubModule(
                    id=module_id,
                    name=str(row["name"]),
                    description=str(row.get("description") or ""),
                    icon=str(row.get("icon") or ""),
                    path=str(row["path"]),
                    category=str(row["category"]),
                    sort_order=int(row.get("sort_order") or 0),
                    enabled=int(row.get("enabled", 1)),
                )
            )
            continue

        existing.name = str(row["name"])
        existing.description = str(row.get("description") or "")
        existing.icon = str(row.get("icon") or "")
        existing.path = str(row["path"])
        existing.category = str(row["category"])
        existing.sort_order = int(row.get("sort_order") or 0)
        existing.enabled = int(row.get("enabled", 1))

    session.flush()


def module_id_for_path(path: str) -> str:
    return _module_id_from_path(path)
