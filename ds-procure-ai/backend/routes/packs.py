"""Pack and insight HTTP surface. Stays off procurement.py so chat routes do not grow."""

from __future__ import annotations

from flask import Blueprint, jsonify, send_file

from services import procurement_packs
from services.request_user import AuthRequiredError, auth_error_response, require_workspace_id

packs_bp = Blueprint("procurement_packs", __name__)


@packs_bp.route("/api/procurement/projects/<project_id>/insights", methods=["GET"])
def project_insights(project_id):
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)
    payload = procurement_packs.insights_for_owner(project_id, owner_id)
    if payload is None:
        return jsonify({"error": "not_found"}), 404
    return jsonify(payload)


@packs_bp.route("/api/procurement/projects/<project_id>/packs", methods=["GET"])
def project_packs(project_id):
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)
    payload = procurement_packs.packs_for_owner(project_id, owner_id)
    if payload is None:
        return jsonify({"error": "not_found"}), 404
    return jsonify(payload)


@packs_bp.route("/api/procurement/projects/<project_id>/packs/<kind>", methods=["POST"])
def start_project_pack(project_id, kind):
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)
    capability = "compare_xlsx" if kind == "xlsx" else "steerco_ppt" if kind == "ppt" else ""
    if not capability:
        return jsonify({"error": "bad_request", "detail": "kind must be xlsx or ppt"}), 400
    payload = procurement_packs.start_pack(project_id, owner_id, capability)
    if payload is None:
        return jsonify({"error": "not_found"}), 404
    return jsonify(payload)


@packs_bp.route("/api/procurement/projects/<project_id>/packs/<kind>/download", methods=["GET"])
def download_project_pack(project_id, kind):
    try:
        owner_id = require_workspace_id()
    except AuthRequiredError as exc:
        return auth_error_response(exc)
    if kind not in {"xlsx", "ppt"}:
        return jsonify({"error": "bad_request", "detail": "kind must be xlsx or ppt"}), 400
    path = procurement_packs.pack_download_path(project_id, owner_id, kind)
    if path is None:
        return jsonify({"error": "not_found"}), 404
    download_name = "comparison_matrix.xlsx" if kind == "xlsx" else "steerco_pack.pptx"
    return send_file(path, as_attachment=True, download_name=download_name)
