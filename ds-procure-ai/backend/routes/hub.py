from datetime import datetime

from flask import Blueprint, jsonify, session

from routes.auth import get_or_resolve_identity
from services.request_user import get_workspace_id
from shared.db.repos.hub import group_modules_by_category, list_modules_for_user
from shared.db.repos.users import upsert_user_from_identity


hub_bp = Blueprint("hub", __name__)


def _welcome_greeting() -> str:
    hour = datetime.now().hour
    if hour < 12:
        period = "Morning"
    elif hour < 17:
        period = "Afternoon"
    else:
        period = "Evening"

    identity = session.get("identity") or {}
    user = identity.get("user") if isinstance(identity, dict) else None
    display = ""
    if isinstance(user, dict):
        display = (user.get("display_name") or user.get("user_name") or "").strip()
    first = display.split()[0] if display else "there"
    return f"{period} {first},"


@hub_bp.route("/api/hub", methods=["GET"])
def hub():
    identity: dict = {}
    try:
        identity = get_or_resolve_identity()
        upsert_user_from_identity(identity)
    except Exception:
        pass

    workspace_id = get_workspace_id()
    if not workspace_id and isinstance(identity, dict):
        user = identity.get("user")
        if isinstance(user, dict):
            workspace_id = str(user.get("id") or "").strip() or None

    if workspace_id:
        categories = group_modules_by_category(list_modules_for_user(workspace_id))
    else:
        categories = group_modules_by_category(list_modules_for_user(""))

    return jsonify({
        "page": "hub",
        "brand": {
            "name": "Mate",
            "logo": "/etex-logo.png",
        },
        "welcome": {
            "greeting": _welcome_greeting(),
            "description": (
                "Start a new chat, generate meeting notes, "
                "or build documents — all powered by AI "
                "to make your work easier."
            ),
            "image": "/assets/hub-hero.png",
        },
        "categories": categories,
        "footer": {
            "logo": "/assets/etex-footer-logo.png",
        },
    })
