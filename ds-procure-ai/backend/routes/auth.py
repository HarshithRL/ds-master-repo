from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from shared.databricks_runtime import bind_obo_from_headers
from shared.db.repos.users import upsert_user_from_identity
from shared.logger_global import get_logger
from services.identity import IdentityError, resolve_identities

auth_bp = Blueprint("auth", __name__)
log = get_logger(__name__)

SESSION_KEY = "identity"


def get_or_resolve_identity() -> dict:
    # Bind visitor OBO before any DB use (incl. identity cache hits).
    bind_obo_from_headers(request.headers)
    cached = session.get(SESSION_KEY)
    obo = (request.headers.get("x-forwarded-access-token") or "").strip()
    if isinstance(cached, dict) and cached.get("user") and cached.get("app"):
        cached_auth = (cached.get("user") or {}).get("auth")
        # Don't keep an SP fallback session once the Apps proxy sends an OBO token.
        if not (obo and cached_auth == "oauth_m2m"):
            log.debug("identity cache hit")
            return cached

    identity = resolve_identities(request)
    payload = identity.to_public_dict()
    session[SESSION_KEY] = payload
    try:
        upsert_user_from_identity(payload)
    except Exception:
        log.exception("user upsert failed workspace_id={}", (payload.get("user") or {}).get("id"))
    log.info(
        "identity resolved runtime={} user_id={}",
        payload.get("env"),
        (payload.get("user") or {}).get("id"),
    )
    return payload


@auth_bp.route("/api/auth", methods=["GET"])
def auth():
    try:
        return jsonify(get_or_resolve_identity())
    except IdentityError as exc:
        log.warning("identity resolve failed: {}", exc)
        return jsonify({"error": str(exc)}), exc.status_code
