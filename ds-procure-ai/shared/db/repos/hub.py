"""Hub module catalog queries."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.db.connection import session_scope
from shared.db.models import HubModule, UserModule


@dataclass(frozen=True)
class HubModuleView:
    id: str
    name: str
    description: str
    icon: str
    path: str
    category: str
    sort_order: int
    enabled: bool
    available: bool


def list_modules_for_user(workspace_id: str) -> list[HubModuleView]:
    with session_scope() as session:
        return _list_modules_for_user(session, workspace_id)


def _list_modules_for_user(session: Session, workspace_id: str) -> list[HubModuleView]:
    granted = set(
        session.scalars(
            select(UserModule.module_id).where(UserModule.workspace_id == workspace_id)
        ).all()
    )
    modules = session.scalars(
        select(HubModule).order_by(HubModule.sort_order, HubModule.name)
    ).all()
    views: list[HubModuleView] = []
    for module in modules:
        enabled = bool(module.enabled)
        views.append(
            HubModuleView(
                id=module.id,
                name=module.name,
                description=module.description or "",
                icon=module.icon or "",
                path=module.path,
                category=module.category,
                sort_order=module.sort_order,
                enabled=enabled,
                available=enabled and module.id in granted,
            )
        )
    return views


def group_modules_by_category(modules: list[HubModuleView]) -> list[dict]:
    categories: dict[str, list[dict]] = {}
    for module in modules:
        tool = {
            "id": module.id,
            "name": module.name,
            "description": module.description,
            "icon": module.icon,
            "path": module.path,
            "available": module.available,
            "status": "active" if module.available else "coming_soon",
        }
        categories.setdefault(module.category, []).append(tool)
    return [
        {"name": name, "tools": tools}
        for name, tools in categories.items()
    ]
