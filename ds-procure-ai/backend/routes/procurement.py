from __future__ import annotations

from flask import Blueprint, Response, jsonify, request, stream_with_context

from routes.auth import get_or_resolve_identity
from shared.db.repos import artifacts as artifact_repo
from shared.db.repos import projects as project_repo
from shared.db.repos.artifacts import ArtifactNotFoundError, UploadFile
from shared.db.repos.projects import ProjectNotFoundError, ProjectValidationError
from shared.db.repos.users import get_user
from shared.logger_global import bind_context, get_logger
from ai_brain.core.kb.extract.ingest import enqueue_ingest
from services import chat_sessions
from services import procurement_chat
from services.procurement_serializers import (
    _display_name,
    dashboard_payload,
    documents_payload,
    nav_payload,
    overview_payload,
    project_shell_payload,
    projects_page_payload,
    requirements_payload,
    vendors_payload,
    workspace_payload,
)
from services.request_user import AuthRequiredError, auth_error_response, require_workspace_id

procurement_bp = Blueprint("procurement", __name__)
log = get_logger(__name__)


def _load_project_or_404(project_id: str, owner_id: str):
    try:
        return project_repo.get_for_owner(project_id, owner_id)
    except ProjectNotFoundError:
        return None


@procurement_bp.route("/api/procurement/nav", methods=["GET"])
def nav():
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)
    identity = get_or_resolve_identity()
    user = get_user(owner_id)
    return jsonify(nav_payload(user, identity))


@procurement_bp.route("/api/procurement/dashboard", methods=["GET"])
def dashboard():
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)
    projects = project_repo.list_all_for_owner(owner_id)
    return jsonify(dashboard_payload(projects))


@procurement_bp.route("/api/procurement/projects", methods=["GET"])
def projects():
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)

    status = request.args.get("status")
    category = request.args.get("category")
    q = request.args.get("q")
    page = int(request.args.get("page", 1) or 1)
    page_size = int(request.args.get("page_size", 50) or 50)
    rows, total = project_repo.list_for_owner(
        owner_id,
        status=status,
        category=category,
        q=q,
        page=page,
        page_size=page_size,
    )
    all_projects = project_repo.list_all_for_owner(owner_id)
    return jsonify(
        projects_page_payload(
            rows,
            total=total,
            page=page,
            page_size=page_size,
            all_projects=all_projects,
        )
    )


@procurement_bp.route("/api/procurement/projects/next-code", methods=["GET"])
def project_next_code():
    try:
        require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)
    return jsonify({"projectId": project_repo.peek_next_code()})


@procurement_bp.route("/api/procurement/projects", methods=["POST"])
def create_project():
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)

    body = request.get_json(silent=True) or {}
    try:
        created = project_repo.create(owner_id, body if isinstance(body, dict) else {})
    except ProjectValidationError as exc:
        log.warning("create project rejected: {}", exc)
        return jsonify({"error": "bad_request", "detail": str(exc)}), 400

    log.info("created project id={}", created.id)
    return jsonify({"id": created.id, "name": created.name, "projectId": created.code}), 201


@procurement_bp.route("/api/procurement/projects/<project_id>", methods=["GET"])
def project_detail(project_id):
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)

    project = _load_project_or_404(project_id, owner_id)
    if not project:
        return jsonify({"error": "not_found"}), 404
    return jsonify(project_shell_payload(project))


@procurement_bp.route("/api/procurement/projects/<project_id>", methods=["PATCH"])
def update_project(project_id):
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)

    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"error": "bad_request", "detail": "JSON body required"}), 400
    try:
        updated = project_repo.update_for_owner(project_id, owner_id, body)
    except ProjectNotFoundError:
        return jsonify({"error": "not_found"}), 404
    return jsonify(project_repo.project_to_dict(updated))


@procurement_bp.route("/api/procurement/projects/<project_id>", methods=["DELETE"])
def delete_project(project_id):
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)

    try:
        project_repo.delete_for_owner(project_id, owner_id)
    except ProjectNotFoundError:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"deleted": True, "id": project_id})


@procurement_bp.route("/api/procurement/projects/<project_id>/files", methods=["POST"])
def upload_project_files(project_id):
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)

    uploads = request.files.getlist("files") or request.files.getlist("file")
    if not uploads:
        return jsonify({"error": "bad_request", "detail": "No files provided"}), 400
    from ai_brain.core.procurement_ai.file_ingest import MAX_FILES, count_files

    incoming = [item for item in uploads if item and item.filename]
    already = count_files(project_id)
    if already + len(incoming) > MAX_FILES:
        return jsonify({
            "error": "bad_request",
            "detail": f"A thread accepts {MAX_FILES} files. This upload would make {already + len(incoming)}.",
        }), 400

    folder = (request.form.get("folder") or artifact_repo.FOLDER_VENDOR).strip()
    created = []
    try:
        for upload in uploads:
            if not upload or not upload.filename:
                continue
            artifact = artifact_repo.create_upload(
                project_id,
                owner_id,
                UploadFile(
                    filename=upload.filename,
                    stream=upload.stream,
                    content_type=upload.content_type,
                ),
                folder=folder,
            )
            created.append(
                {
                    "id": artifact.id,
                    "name": artifact.original_name,
                    "folder": artifact.folder,
                    "parseStatus": artifact.parse_status or "pending",
                    "parseError": artifact.parse_error,
                }
            )
    except ProjectNotFoundError:
        return jsonify({"error": "not_found"}), 404

    if created:
        enqueue_ingest(project_id, [item["id"] for item in created])

    log.info("files queued project_id={} count={} parse=enqueued", project_id, len(created))
    return jsonify({"uploaded": created}), 202


@procurement_bp.route(
    "/api/procurement/projects/<project_id>/files/<artifact_id>",
    methods=["DELETE"],
)
def delete_project_file(project_id, artifact_id):
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)

    try:
        artifact_repo.delete_for_owner(artifact_id, owner_id)
    except ArtifactNotFoundError:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"deleted": True, "id": artifact_id, "project_id": project_id})


@procurement_bp.route(
    "/api/procurement/projects/<project_id>/overview",
    methods=["GET"],
)
def project_overview(project_id):
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)

    project = _load_project_or_404(project_id, owner_id)
    if not project:
        return jsonify({"error": "not_found"}), 404
    artifacts = artifact_repo.list_for_project(project_id, owner_id)
    return jsonify(overview_payload(project, artifacts))


@procurement_bp.route(
    "/api/procurement/projects/<project_id>/requirements",
    methods=["GET"],
)
def project_requirements(project_id):
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)

    project = _load_project_or_404(project_id, owner_id)
    if not project:
        return jsonify({"error": "not_found"}), 404
    return jsonify(requirements_payload(project_id))


@procurement_bp.route(
    "/api/procurement/projects/<project_id>/vendors",
    methods=["GET"],
)
def project_vendors(project_id):
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)

    project = _load_project_or_404(project_id, owner_id)
    if not project:
        return jsonify({"error": "not_found"}), 404
    return jsonify(vendors_payload(project_id))


@procurement_bp.route(
    "/api/procurement/projects/<project_id>/notes",
    methods=["GET"],
)
def project_notes(project_id):
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)

    if not _load_project_or_404(project_id, owner_id):
        return jsonify({"error": "not_found"}), 404

    from shared.db.repos import notes as note_repo

    bid_id = (request.args.get("bid_id") or "").strip() or None
    return jsonify({"notes": note_repo.list_for_project(project_id, bid_id=bid_id)})


@procurement_bp.route(
    "/api/procurement/projects/<project_id>/notes",
    methods=["POST"],
)
def create_project_note(project_id):
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)

    if not _load_project_or_404(project_id, owner_id):
        return jsonify({"error": "not_found"}), 404

    from shared.db.repos import notes as note_repo

    body = request.get_json(silent=True) or {}
    try:
        note = note_repo.create(
            project_id,
            str(body.get("body") or ""),
            bid_id=(str(body.get("bid_id") or "").strip() or None),
            kind=str(body.get("kind") or "note"),
            source=str(body.get("source") or "manual"),
            author=str(body.get("author") or "") or None,
        )
    except ValueError as exc:
        return jsonify({"error": "bad_request", "detail": str(exc)}), 400
    _sync_notes_corpus(project_id)
    return jsonify(note), 201


def _sync_notes_corpus(project_id: str) -> None:
    """Notes reach chat only as chunks, and kb_build is far too slow to be the
    only thing that puts them there."""
    try:
        from ai_brain.core.kb.extract.notes_corpus import materialize_notes

        materialize_notes(project_id)
    except Exception:  # noqa: BLE001
        log.exception("notes corpus sync failed project_id={}", project_id)


@procurement_bp.route(
    "/api/procurement/projects/<project_id>/notes/<note_id>",
    methods=["PATCH", "DELETE"],
)
def modify_project_note(project_id, note_id):
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)

    if not _load_project_or_404(project_id, owner_id):
        return jsonify({"error": "not_found"}), 404

    from shared.db.repos import notes as note_repo

    try:
        if request.method == "DELETE":
            note_repo.delete(project_id, note_id)
            _sync_notes_corpus(project_id)
            return jsonify({"deleted": True, "id": note_id})
        body = request.get_json(silent=True) or {}
        updated = note_repo.update(project_id, note_id, str(body.get("body") or ""))
    except note_repo.NoteNotFoundError:
        return jsonify({"error": "not_found"}), 404
    except ValueError as exc:
        return jsonify({"error": "bad_request", "detail": str(exc)}), 400
    _sync_notes_corpus(project_id)
    return jsonify(updated)


@procurement_bp.route(
    "/api/procurement/projects/<project_id>/vendors/<bid_id>",
    methods=["PATCH"],
)
def update_project_vendor(project_id, bid_id):
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)

    project = _load_project_or_404(project_id, owner_id)
    if not project:
        return jsonify({"error": "not_found"}), 404

    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict) or "shortlisted" not in body:
        return jsonify({"error": "bad_request", "detail": "shortlisted required"}), 400

    from shared.db.repos import vendors as vendor_repo

    shortlisted = bool(body.get("shortlisted"))
    vendor_repo.set_shortlisted(project_id, bid_id, shortlisted)
    return jsonify({"bid_id": bid_id, "shortlisted": shortlisted})


@procurement_bp.route(
    "/api/procurement/projects/<project_id>/requirements/<requirement_id>/vendors/<bid_id>",
    methods=["PATCH", "DELETE"],
)
def review_project_evidence(project_id, requirement_id, bid_id):
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)

    if not _load_project_or_404(project_id, owner_id):
        return jsonify({"error": "not_found"}), 404

    from shared.db.repos import evidence as evidence_repo

    try:
        if request.method == "DELETE":
            evidence_repo.clear_review(project_id, requirement_id, bid_id)
            return jsonify({"cleared": True})

        body = request.get_json(silent=True) or {}
        user = get_user(owner_id)
        reviewer = _display_name(user, get_or_resolve_identity())
        return jsonify(
            evidence_repo.set_review(
                project_id,
                requirement_id,
                bid_id,
                status=str(body.get("status") or ""),
                note=str(body.get("note") or ""),
                reviewed_by=reviewer,
            )
        )
    except evidence_repo.EvidenceNotFoundError:
        return jsonify({"error": "not_found"}), 404
    except ValueError as exc:
        return jsonify({"error": "bad_request", "detail": str(exc)}), 400


@procurement_bp.route(
    "/api/procurement/projects/<project_id>/documents",
    methods=["GET"],
)
def project_documents(project_id):
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)

    project = _load_project_or_404(project_id, owner_id)
    if not project:
        return jsonify({"error": "not_found"}), 404
    artifacts = artifact_repo.list_for_project(project_id, owner_id)
    try:
        from ai_brain.core.procurement_ai.packs import store as pack_store

        packs = pack_store.pack_status(project_id)
    except Exception:
        log.exception("pack status unavailable for documents project_id={}", project_id)
        packs = None
    return jsonify(documents_payload(artifacts, packs))


@procurement_bp.route(
    "/api/procurement/projects/<project_id>/workspace",
    methods=["GET"],
)
def project_workspace(project_id):
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)

    project = _load_project_or_404(project_id, owner_id)
    if not project:
        return jsonify({"error": "not_found"}), 404
    artifacts = artifact_repo.list_for_project(project_id, owner_id)
    identity = get_or_resolve_identity()
    user = get_user(owner_id)
    initial = nav_payload(user, identity)["user"]["initial"]
    return jsonify(workspace_payload(project, artifacts, user_initial=initial))


@procurement_bp.route(
    "/api/procurement/projects/<project_id>/workspace/chat",
    methods=["POST"],
)
def project_workspace_chat(project_id):
    bind_context(project_id=project_id, workflow="chat.http")
    body = request.get_json(silent=True) or {}
    message = body.get("message")
    history = body.get("history")
    log.info("workspace chat POST project_id={}", project_id)

    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)

    try:
        reply = procurement_chat.run_workspace_chat(
            project_id,
            owner_id=owner_id,
            message=message if isinstance(message, str) else "",
            history=history if isinstance(history, list) else None,
        )
    except ValueError as exc:
        log.warning("workspace chat bad request: {}", exc)
        return jsonify({"error": "bad_request", "detail": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        log.exception("workspace chat agent failed")
        return jsonify(
            {
                "error": "agent_failed",
                "detail": f"{type(exc).__name__}: {str(exc)[:300]}",
            }
        ), 500

    if reply is None:
        log.warning("workspace chat project not found project_id={}", project_id)
        return jsonify({"error": "not_found"}), 404
    return jsonify(reply)


@procurement_bp.route(
    "/api/procurement/projects/<project_id>/workspace/sessions",
    methods=["GET"],
)
def project_chat_sessions(project_id):
    bind_context(project_id=project_id, workflow="chat.sessions")
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)
    if project_repo.get_for_owner_or_none(project_id, owner_id) is None:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"sessions": chat_sessions.list_sessions(project_id)})


@procurement_bp.route(
    "/api/procurement/projects/<project_id>/workspace/sessions",
    methods=["POST"],
)
def project_chat_session_create(project_id):
    bind_context(project_id=project_id, workflow="chat.session_create")
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)
    if project_repo.get_for_owner_or_none(project_id, owner_id) is None:
        return jsonify({"error": "not_found"}), 404
    body = request.get_json(silent=True) or {}
    title = body.get("title") if isinstance(body.get("title"), str) else "New chat"
    return jsonify(chat_sessions.create_session(project_id, title=title)), 201


@procurement_bp.route(
    "/api/procurement/projects/<project_id>/workspace/sessions/<session_id>",
    methods=["GET"],
)
def project_chat_session_get(project_id, session_id):
    bind_context(project_id=project_id, workflow="chat.session_get")
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)
    if project_repo.get_for_owner_or_none(project_id, owner_id) is None:
        return jsonify({"error": "not_found"}), 404
    found = chat_sessions.get_session(project_id, session_id)
    if found is None:
        return jsonify({"error": "not_found"}), 404
    return jsonify(found)


@procurement_bp.route(
    "/api/procurement/projects/<project_id>/workspace/chat/stream",
    methods=["POST"],
)
def project_workspace_chat_stream(project_id):
    bind_context(project_id=project_id, workflow="chat.http_stream")
    body = request.get_json(silent=True) or {}
    message = body.get("message") if isinstance(body.get("message"), str) else ""
    history = body.get("history") if isinstance(body.get("history"), list) else None
    session_id = body.get("session_id") if isinstance(body.get("session_id"), str) else None

    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)

    if project_repo.get_for_owner_or_none(project_id, owner_id) is None:
        log.warning("workspace chat stream project not found project_id={}", project_id)
        return jsonify({"error": "not_found"}), 404

    log.info("workspace chat stream POST project_id={}", project_id)

    @stream_with_context
    def generate():
        for event in procurement_chat.iter_workspace_chat_events(
            project_id,
            owner_id=owner_id,
            message=message,
            history=history,
            session_id=session_id,
        ):
            yield procurement_chat.sse_format(event)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# No `/workspace/responses` route here by design: the old durable-response
# proxy (`post_response`) used a 10s brain timeout and caused chat 502s.
# Use `/workspace/chat` (sync) or `/workspace/chat/stream` (SSE) instead.
@procurement_bp.route(
    "/api/procurement/projects/<project_id>/workspace/chat/resume",
    methods=["POST"],
)
def project_workspace_chat_resume(project_id):
    """Pass-through to brain `POST /v1/threads/{id}/resume`."""
    bind_context(project_id=project_id, workflow="chat.http_resume")
    body = request.get_json(silent=True) or {}
    if "resume" not in body:
        return jsonify({"error": "bad_request", "detail": "resume is required"}), 400
    resume = body.get("resume")
    checkpoint_id = body.get("checkpoint_id")
    if checkpoint_id is not None and not isinstance(checkpoint_id, str):
        checkpoint_id = str(checkpoint_id)

    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)

    if project_repo.get_for_owner_or_none(project_id, owner_id) is None:
        log.warning("workspace chat resume project not found project_id={}", project_id)
        return jsonify({"error": "not_found"}), 404

    accept = request.headers.get("Accept") or ""
    wants_stream = "text/event-stream" in accept or body.get("stream") is True
    log.info("workspace chat resume POST project_id={} stream={}", project_id, wants_stream)

    if wants_stream:

        @stream_with_context
        def generate():
            for event in procurement_chat.iter_workspace_resume_events(
                project_id,
                owner_id=owner_id,
                resume=resume,
                checkpoint_id=checkpoint_id,
            ):
                yield procurement_chat.sse_format(event)

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    try:
        result = procurement_chat.run_workspace_resume(
            project_id,
            owner_id=owner_id,
            resume=resume,
            checkpoint_id=checkpoint_id,
        )
    except ValueError as exc:
        log.warning("workspace chat resume bad request: {}", exc)
        return jsonify({"error": "bad_request", "detail": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        log.exception("workspace chat resume failed")
        return jsonify(
            {
                "error": "agent_failed",
                "detail": f"{type(exc).__name__}: {str(exc)[:300]}",
            }
        ), 500

    if result is None:
        return jsonify({"error": "not_found"}), 404
    return jsonify(result)
