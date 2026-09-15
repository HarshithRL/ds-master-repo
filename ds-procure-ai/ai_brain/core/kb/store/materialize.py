"""Assemble a virtual `/project/{code}/...` tree for deep-agent StateBackend.

This is assembly, not generation: `document.markdown` already carries
`## Page N` sections. `artifact.vendor_id` is the *bid* id (consortium is
not a single vendor — legal entities live in `vendor`, membership in the
graph at W7).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from sqlalchemy import select

from ai_brain.core.procurement_ai.project_context import load_artifacts, load_project
from shared.db.connection import session_scope
from shared.db.models import Artifact, QualityFlag, Vendor

# Plan W4 maps rfp/registry/csr/proposal. classify.py also emits `pricing`;
# those files are vendor-scoped, so they follow the bid folder.
_ROLE_FOLDER = {
    "rfp": "rfp",
    "registry": "vendors/{bid}",
    "csr": "vendors/{bid}",
    "proposal": "vendors/{bid}",
    "pricing": "vendors/{bid}",
}
_UNASSIGNED_BID = "_unassigned"


def project_files(project_id: str) -> dict[str, str]:
    """Return path → markdown text for one project. Paths start with `/`."""
    project = load_project(project_id)
    if project is None:
        return {}
    code = project.code
    artifacts = load_artifacts(project.id)
    flags_by_artifact = _flags_by_artifact(project.id)
    files: dict[str, str] = {}
    used_paths: set[str] = set()
    for artifact in artifacts:
        if (artifact.parse_status or "").strip() != "ok":
            path = f"/project/{code}/_quality/{artifact.id}.md"
            files[path] = quality_note(artifact, flags_by_artifact.get(artifact.id, []))
            used_paths.add(path)
            continue
        markdown = _document_markdown(artifact.parsed_json, artifact=artifact)
        if markdown is None:
            path = f"/project/{code}/_quality/{artifact.id}.md"
            files[path] = quality_note(
                artifact,
                flags_by_artifact.get(artifact.id, []),
                extra="parse_status=ok but parsed_json has no usable markdown",
            )
            used_paths.add(path)
            continue
        folder = _folder_for(artifact)
        slug = _unique_path(
            f"/project/{code}/{folder}/{_slug_filename(artifact.original_name)}",
            used_paths,
            artifact.id,
        )
        files[slug] = markdown
        used_paths.add(slug)
    files[f"/project/{code}/README.md"] = readme(project.id, project.code, artifacts, flags_by_artifact)
    return files


def list_bid_ids(project_id: str) -> list[str]:
    """Distinct bid ids from `artifact.vendor_id`, never `vendor.id`."""
    project = load_project(project_id)
    if project is None:
        return []
    bids: set[str] = set()
    for artifact in load_artifacts(project.id):
        bid = (artifact.vendor_id or "").strip()
        if bid:
            bids.add(bid)
    return sorted(bids)


def vendor_paths(project_id: str, bid_id: str) -> list[str]:
    """Filesystem paths under `/project/{code}/vendors/{bid_id}/`."""
    project = load_project(project_id)
    if project is None:
        return []
    prefix = f"/project/{project.code}/vendors/{bid_id}/"
    return sorted(path for path in project_files(project.id) if path.startswith(prefix))


def quality_note(
    artifact: Artifact,
    flags: list[QualityFlag] | None = None,
    extra: str | None = None,
) -> str:
    lines = [
        f"# Parse quality — {artifact.original_name}",
        "",
        f"- artifact_id: `{artifact.id}`",
        f"- parse_status: `{artifact.parse_status or 'NULL'}`",
        f"- bid_id (artifact.vendor_id): `{artifact.vendor_id or ''}`",
        f"- doc_role: `{artifact.doc_role or ''}`",
    ]
    if artifact.parse_error:
        lines.append(f"- parse_error: {artifact.parse_error}")
    if extra:
        lines.append(f"- note: {extra}")
    if flags:
        lines.extend(["", "## Detector flags"])
        for flag in flags:
            lines.append(f"- `{flag.kind}` ({flag.severity or 'n/a'}): {flag.detail or ''}")
    lines.append("")
    return "\n".join(lines)


def readme(
    project_id: str,
    code: str,
    artifacts: list[Artifact] | None = None,
    flags_by_artifact: dict[str, list[QualityFlag]] | None = None,
) -> str:
    if artifacts is None:
        artifacts = load_artifacts(project_id)
    if flags_by_artifact is None:
        flags_by_artifact = _flags_by_artifact(project_id)
    roster = _roster_entities(project_id)
    bids = sorted({(a.vendor_id or "").strip() for a in artifacts if (a.vendor_id or "").strip()})
    lines = [
        f"# Project {code}",
        "",
        "Virtual tree for extraction agents. `artifact.vendor_id` is the **bid** id.",
        "A consortium is one bid with multiple legal entities — never a single vendor_id.",
        "",
        "## Roster (legal entities)",
    ]
    if roster:
        lines.extend(f"- {name}" + (f" (`{registry}`)" if registry else "") for name, registry in roster)
    else:
        lines.append("- (none confirmed)")
    lines.extend(["", "## Bids (from artifact.vendor_id)"])
    if bids:
        lines.extend(f"- `{bid}`" for bid in bids)
    else:
        lines.append("- (none classified)")
    lines.extend(["", "## Inventory"])
    for artifact in artifacts:
        role = artifact.doc_role or "unclassified"
        status = artifact.parse_status or "NULL"
        bid = artifact.vendor_id or ""
        lines.append(
            f"- `{artifact.original_name}` — role={role} status={status} bid=`{bid}` id=`{artifact.id}`"
        )
    lines.extend(["", "## Quality flags"])
    any_flag = False
    for artifact_id, flags in sorted(flags_by_artifact.items()):
        for flag in flags:
            any_flag = True
            lines.append(f"- `{artifact_id}` `{flag.kind}`: {flag.detail or ''}")
    if not any_flag:
        lines.append("- (none)")
    lines.append("")
    return "\n".join(lines)


def _folder_for(artifact: Artifact) -> str:
    template = _ROLE_FOLDER.get(artifact.doc_role or "", "reference")
    bid = (artifact.vendor_id or "").strip() or _UNASSIGNED_BID
    return template.format(bid=bid)


def _document_markdown(
    parsed_json: str | None,
    *,
    artifact: Artifact | None = None,
) -> str | None:
    if parsed_json:
        try:
            data = json.loads(parsed_json)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            markdown = data.get("markdown")
            if isinstance(markdown, str) and markdown.strip():
                return markdown
            # Legacy ingest wrote markdown_relpath only (no markdown body).
            rel_name = data.get("markdown_relpath")
            if artifact is not None and isinstance(rel_name, str) and rel_name.strip():
                from shared.db.paths import artifact_absolute_path

                base = artifact.parsed_relpath or ""
                if base:
                    candidate = artifact_absolute_path(base).with_name(Path(rel_name).name)
                    from shared.db.volume_fs import exists as vol_exists, read_text as vol_read_text
                    if vol_exists(candidate):
                        text = vol_read_text(candidate)
                        if text.strip():
                            return text
    if artifact is not None and artifact.parsed_relpath:
        from shared.db.paths import artifact_absolute_path

        md_path = artifact_absolute_path(artifact.parsed_relpath).with_suffix(".md")
        from shared.db.volume_fs import exists as vol_exists, read_text as vol_read_text
        if vol_exists(md_path):
            text = vol_read_text(md_path)
            if text.strip():
                return text
    return None


def _slug_filename(original_name: str) -> str:
    stem = Path(original_name or "document").stem
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", stem).strip("-").lower() or "document"
    return f"{slug}.md"


def _unique_path(path: str, used: set[str], artifact_id: str) -> str:
    if path not in used:
        return path
    stem = path[:-3] if path.endswith(".md") else path
    return f"{stem}-{artifact_id}.md"


def _flags_by_artifact(project_id: str) -> dict[str, list[QualityFlag]]:
    with session_scope() as session:
        rows = session.scalars(
            select(QualityFlag).where(QualityFlag.project_id == project_id)
        ).all()
        grouped: dict[str, list[QualityFlag]] = {}
        for row in rows:
            session.expunge(row)
            key = row.artifact_id or "_project"
            grouped.setdefault(key, []).append(row)
        return grouped


def _roster_entities(project_id: str) -> list[tuple[str, str | None]]:
    with session_scope() as session:
        rows = session.scalars(select(Vendor).where(Vendor.project_id == project_id)).all()
        out = [(row.name, row.registry_id) for row in rows]
    return sorted(out, key=lambda item: item[0].lower())
