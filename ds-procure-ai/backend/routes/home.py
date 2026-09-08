from flask import Blueprint, jsonify

home_bp = Blueprint("home", __name__)


@home_bp.route("/api/home", methods=["GET"])
def home():
    return jsonify({
        "page": "home",
        "heading": "Connected"
    })