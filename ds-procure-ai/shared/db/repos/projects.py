"""Project CRUD scoped to owner and module."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import date
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from shared.db.connection import session_scope
from shared.db.models import AppUser, Project, utc_now_iso
from shared.db.paths import project_root
from shared.db.seed import PROCUREMENT_MODULE_ID

DEFAULT_PAGE_SIZE = 50
UNTITLED = "untitled"

WORKFLOW_ENTRY_POINTS = (
    "Sourcing",
    "Vendor Comparison",
    "Contract Negotiation",
)
BUSINESS_PROCESSES = ("Indirect", "Direct")


class ProjectNotFoundError(LookupError):
    pass


class ProjectValidationError(ValueError):
    pass


def peek_next_code() -> str:
    """Return the next project code without inserting a row."""
    with session_scope() as session:
        return _next_code(session)


def create(owner_id: str, payload: dict[str, Any], *, module_id: str = PROCUREMENT_MODULE_ID) -> Project:
    name = _text_or_untitled(payload.get("name"))
    workflow_entry_point = _validate_workflow_entry_point(payload.get("workflowEntryPoint"))
    business_process = _validate_business_process(payload.get("businessProcess"))

    requirements = payload.get("requirements")
    requirements_json = None
    if isinstance(requirements, list):
        requirements_json = json.dumps(requirements)

    with session_scope() as session:
        requested_code = payload.get("projectId") or payload.get("code")
        code = _resolve_code(session, requested_code)
        now = utc_now_iso()
        project = Project(
            id=str(uuid.uuid4()),
            code=code,
            owner_id=owner_id,
            module_id=module_id,
            name=name,
            workflow_entry_point=workflow_entry_point,
            business_process=business_process,
            requester=_text_or_untitled(payload.get("requester")),
            dept=_text_or_untitled(payload.get("dept")),
            category=_text_or_untitled(payload.get("category")),
            region=_text_or_untitled(payload.get("region")),
            status="Active",
            priority="Medium",
            budget=_format_budget(payload.get("targetSpend")),
            award_horizon=_text_or_untitled(payload.get("awardHorizon")),
            description=_text_or_untitled(payload.get("description")),
            progress=0,
            deadline="—",
            requirements_json=requirements_json,
            created_at=now,
            updated_at=now,
        )
        session.add(project)
        session.flush()
        _ensure_project_dirs(project.id)
        session.refresh(project, attribute_names=["owner"])
        return _detach_project(session, project)


def get_for_owner(project_id: str, owner_id: str, *, module_id: str = PROCUREMENT_MODULE_ID) -> Project:
    with session_scope() as session:
        project = _get_for_owner(session, project_id, owner_id, module_id=module_id)
        if project is None:
            raise ProjectNotFoundError(project_id)
        return _detach_project(session, project)


def get_for_owner_or_none(
    project_id: str,
    owner_id: str | None = None,
    *,
    module_id: str = PROCUREMENT_MODULE_ID,
) -> Project | None:
    with session_scope() as session:
        if owner_id:
            project = _get_for_owner(session, project_id, owner_id, module_id=module_id)
        else:
            project = session.scalar(
                select(Project)
                .options(joinedload(Project.owner))
                .where(Project.id == project_id, Project.module_id == module_id)
            )
        if project is None:
            return None
        return _detach_project(session, project)


def list_for_owner(
    owner_id: str,
    *,
    module_id: str = PROCUREMENT_MODULE_ID,
    status: str | None = None,
    category: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> tuple[list[Project], int]:
    page = max(page, 1)
    page_size = max(min(page_size, 100), 1)

    with session_scope() as session:
        query = (
            select(Project)
            .options(joinedload(Project.owner))
            .where(Project.owner_id == owner_id, Project.module_id == module_id)
            .order_by(Project.created_at.desc())
        )
        if status and status.lower() != "all":
            query = query.where(func.lower(Project.status) == status.lower())
        if category and category.lower() != "all":
            query = query.where(func.lower(Project.category).like(f"%{category.lower()}%"))
        if q:
            needle = f"%{q.strip().lower()}%"
            query = query.where(
                or_(
                    func.lower(Project.name).like(needle),
                    func.lower(Project.code).like(needle),
                    func.lower(Project.category).like(needle),
                )
            )

        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = session.scalars(
            query.offset((page - 1) * page_size).limit(page_size)
        ).unique().all()
        return [_detach_project(session, row) for row in rows], int(total)


def list_all_for_owner(
    owner_id: str,
    *,
    module_id: str = PROCUREMENT_MODULE_ID,
) -> list[Project]:
    projects, _ = list_for_owner(owner_id, module_id=module_id, page_size=10_000)
    return projects


def update_for_owner(
    project_id: str,
    owner_id: str,
    fields: dict[str, Any],
    *,
    module_id: str = PROCUREMENT_MODULE_ID,
) -> Project:
    allowed = {
        "name",
        "workflow_entry_point",
        "business_process",
        "requester",
        "dept",
        "category",
        "region",
        "status",
        "priority",
        "budget",
        "award_horizon",
        "description",
        "progress",
        "deadline",
        "requirements",
    }
    api_key_map = {
        "workflowEntryPoint": "workflow_entry_point",
        "businessProcess": "business_process",
        "awardHorizon": "award_horizon",
        "targetSpend": "budget",
    }
    with session_scope() as session:
        project = _get_for_owner(session, project_id, owner_id, module_id=module_id)
        if project is None:
            raise ProjectNotFoundError(project_id)

        for key, value in fields.items():
            attr = api_key_map.get(key, key)
            if attr not in allowed:
                continue
            if attr == "name":
                if not _is_real_value(value):
                    continue
                project.name = str(value).strip()
                continue
            if attr == "workflow_entry_point":
                if not _is_real_value(value):
                    continue
                project.workflow_entry_point = _validate_workflow_entry_point(value)
                continue
            if attr == "business_process":
                if not _is_real_value(value):
                    continue
                project.business_process = _validate_business_process(value)
                continue
            if attr == "requirements":
                if isinstance(value, list) and value:
                    project.requirements_json = json.dumps(value)
                continue
            if attr == "budget":
                if not _is_real_value(value):
                    continue
                project.budget = _format_budget(value)
                continue
            if attr == "progress" and value is not None:
                project.progress = max(0, min(100, int(value)))
                continue
            if attr in {"requester", "dept", "region", "award_horizon", "description", "category"}:
                if not _is_real_value(value):
                    continue
                setattr(project, attr, str(value).strip())
                continue
            if not _is_real_value(value):
                continue
            setattr(project, attr, value)

        project.updated_at = utc_now_iso()
        session.flush()
        session.refresh(project, attribute_names=["owner"])
        return _detach_project(session, project)


def delete_for_owner(
    project_id: str,
    owner_id: str,
    *,
    module_id: str = PROCUREMENT_MODULE_ID,
) -> None:
    with session_scope() as session:
        project = _get_for_owner(session, project_id, owner_id, module_id=module_id)
        if project is None:
            raise ProjectNotFoundError(project_id)
        session.delete(project)
        session.flush()

    root = project_root(project_id)
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)


def project_to_dict(project: Project) -> dict[str, Any]:
    owner_name = _owner_display_name(project.owner)
    return {
        "id": project.id,
        "name": project.name,
        "projectId": project.code,
        "code": project.code,
        "workflowEntryPoint": project.workflow_entry_point or "",
        "businessProcess": project.business_process or "",
        "requester": project.requester or "",
        "dept": project.dept or "",
        "category": project.category or "",
        "owner": owner_name,
        "status": project.status,
        "priority": project.priority,
        "budget": project.budget or "—",
        "progress": project.progress,
        "created": _format_short_date(project.created_at),
        "deadline": project.deadline or "—",
        "region": project.region or "",
        "awardHorizon": project.award_horizon or "",
        "description": project.description or "",
    }


def _get_for_owner(
    session: Session,
    project_id: str,
    owner_id: str,
    *,
    module_id: str,
) -> Project | None:
    return session.scalar(
        select(Project)
        .options(joinedload(Project.owner))
        .where(
            Project.id == project_id,
            Project.owner_id == owner_id,
            Project.module_id == module_id,
        )
    )


def _detach_project(session: Session, project: Project) -> Project:
    """Expunge project + owner so attribute access works outside the session."""
    from sqlalchemy import inspect as sa_inspect

    owner = project.owner
    if owner is not None:
        owner_state = sa_inspect(owner)
        if not owner_state.detached:
            # Touch scalar attrs while still attached so they stay loaded after expunge.
            _ = (owner.display_name, owner.user_name, owner.email)
            session.expunge(owner)
    if not sa_inspect(project).detached:
        session.expunge(project)
    return project


def _next_code(session: Session) -> str:
    year = date.today().year
    prefix = f"PRJ-{year}-"
    codes = session.scalars(
        select(Project.code).where(Project.code.like(f"{prefix}%"))
    ).all()
    highest = 0
    for code in codes:
        try:
            highest = max(highest, int(str(code)[len(prefix) :]))
        except ValueError:
            continue
    return f"{prefix}{highest + 1:04d}"


def _resolve_code(session: Session, requested: object) -> str:
    text = str(requested or "").strip()
    if text and _is_valid_code_format(text) and not _code_exists(session, text):
        return text
    return _next_code(session)


def _is_valid_code_format(code: str) -> bool:
    parts = code.split("-")
    if len(parts) != 3 or parts[0] != "PRJ":
        return False
    if not parts[1].isdigit() or len(parts[1]) != 4:
        return False
    if not parts[2].isdigit() or len(parts[2]) != 4:
        return False
    return True


def _code_exists(session: Session, code: str) -> bool:
    return session.scalar(select(Project.id).where(Project.code == code)) is not None


def _text_or_untitled(value: object) -> str:
    text = str(value or "").strip()
    return text or UNTITLED


def _is_real_value(value: object) -> bool:
    text = str(value or "").strip()
    return bool(text) and text.lower() != UNTITLED


def _validate_workflow_entry_point(value: object) -> str:
    text = str(value or "").strip()
    if not text or text.lower() == UNTITLED:
        return UNTITLED
    if text not in WORKFLOW_ENTRY_POINTS:
        raise ProjectValidationError(
            f"workflowEntryPoint must be one of: {', '.join(WORKFLOW_ENTRY_POINTS)}"
        )
    return text


def _validate_business_process(value: object) -> str:
    text = str(value or "").strip()
    if not text or text.lower() == UNTITLED:
        return UNTITLED
    if text not in BUSINESS_PROCESSES:
        raise ProjectValidationError(
            f"businessProcess must be one of: {', '.join(BUSINESS_PROCESSES)}"
        )
    return text


def _format_budget(raw: object) -> str:
    text = str(raw or "").strip()
    if not text:
        return "—"
    digits = text.replace(",", "").replace("€", "").replace("$", "").strip()
    try:
        amount = float(digits)
    except ValueError:
        return text
    if amount.is_integer():
        return f"${int(amount):,}"
    return f"${amount:,.2f}"


def _format_short_date(iso_value: str | None) -> str:
    if not iso_value:
        return "—"
    try:
        parsed = date.fromisoformat(iso_value[:10])
    except ValueError:
        return iso_value[:10]
    return f"{parsed.strftime('%b')} {parsed.day}, {parsed.year}"


def _owner_display_name(owner: AppUser | None) -> str:
    if owner is None:
        return "—"
    return owner.display_name or owner.user_name or owner.email or "—"


def _ensure_project_dirs(project_id: str) -> None:
    root = project_root(project_id)
    for subdir in ("uploads", "generated", "parsed"):
        (root / subdir).mkdir(parents=True, exist_ok=True)
