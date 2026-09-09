from flask import Blueprint, jsonify

about_bp = Blueprint("about", __name__)


@about_bp.route("/api/about", methods=["GET"])
def about():
    return jsonify({
        "page": "about",
        "heading": "About"
    })