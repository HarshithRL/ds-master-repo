from __future__ import annotations

import hashlib
import os
import sys
import time
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.logger_global import bind_context, get_logger, reset_context, setup_logging

setup_logging(service="backend")
log = get_logger(__name__)

from shared.db import init_db

init_db()
log.info("sqlite database initialized path={}", os.getenv("MATE_SQLITE_PATH", "mate.sqlite"))

from flask import Flask, g, jsonify, request, send_from_directory
from flask_cors import CORS

from routes import (
    about_bp,
    auth_bp,
    firstview_bp,
    home_bp,
    hub_bp,
    logs_bp,
    packs_bp,
    procurement_bp,
)

_DIST = _REPO_ROOT / "frontend" / "dist"
_DEV_SECRET = "mate-dev-insecure-secret"


def _flask_secret_key() -> str:
    explicit = os.getenv("FLASK_SECRET_KEY", "").strip()
    if explicit:
        return explicit
    app_name = os.getenv("DATABRICKS_APP_NAME", "").strip()
    if app_name:
        seed = os.getenv("DATABRICKS_CLIENT_ID") or app_name
        return hashlib.sha256(f"mate-flask-secret:{seed}".encode()).hexdigest()
    return _DEV_SECRET


app = Flask(__name__)
app.secret_key = _flask_secret_key()
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = bool(os.getenv("DATABRICKS_APP_NAME"))

CORS(
    app,
    supports_credentials=True,
    origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
    ],
    expose_headers=["X-Request-Id"],
)

app.register_blueprint(firstview_bp)
app.register_blueprint(home_bp)
app.register_blueprint(about_bp)
app.register_blueprint(hub_bp)
app.register_blueprint(procurement_bp)
app.register_blueprint(packs_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(logs_bp)


@app.before_request
def _log_request_start() -> None:
    request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
    g.request_id = request_id
    g.request_start = time.perf_counter()
    bind_context(request_id=request_id, workflow="http.request")


@app.after_request
def _log_request_end(response):
    request_id = getattr(g, "request_id", None)
    if request_id:
        response.headers["X-Request-Id"] = request_id

    start = getattr(g, "request_start", None)
    duration_ms = round((time.perf_counter() - start) * 1000, 2) if start else None

    if request.path != "/api/logs":
        log.info(
            "http {} {} -> {} duration_ms={}",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
        )

    reset_context()
    return response


@app.errorhandler(Exception)
def _log_unhandled_error(exc: Exception):
    log.exception("unhandled error on {} {}: {}", request.method, request.path, exc)
    reset_context()
    return jsonify({"error": "internal_error", "detail": str(exc)[:300]}), 500


@app.get("/api/app-context")
def get_app_context():
    return jsonify({
        "brand": "etex",
        "product": "Mate",
        "tagline": "Your Everyday AI Assistant — Securely Built for Etex.",
        "learn_more_text": "Learn more",
        "login_text": "Log in",
    })


def _register_spa() -> None:
    index = _DIST / "index.html"
    if not index.is_file():
        log.warning("frontend dist missing at {}; SPA routes disabled", _DIST)
        return

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def spa(path: str):
        if path.startswith("api/"):
            return jsonify({"error": "not_found"}), 404
        candidate = (_DIST / path).resolve()
        try:
            candidate.relative_to(_DIST.resolve())
        except ValueError:
            return jsonify({"error": "not_found"}), 404
        if path and candidate.is_file():
            return send_from_directory(_DIST, path)
        return send_from_directory(_DIST, "index.html")


_register_spa()


if __name__ == "__main__":
    log.info("starting Flask backend on 127.0.0.1:5000")
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
    )
