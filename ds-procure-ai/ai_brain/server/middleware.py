"""CORS, request-id, optional API key."""

from __future__ import annotations

import os
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shared.logger_global import bind_context, reset_context

_PUBLIC_PATHS = {"/health", "/ready", "/agent/info"}


def install_middleware(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5175",
            "http://127.0.0.1:5175",
        ],
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept", "Authorization", "X-API-Key", "X-Request-Id"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        bind_context(request_id=request_id, workflow="ai_brain")
        try:
            api_key = os.getenv("BRAIN_API_KEY", "").strip()
            if api_key and request.url.path not in _PUBLIC_PATHS and request.method != "OPTIONS":
                provided = request.headers.get("x-api-key") or ""
                auth = request.headers.get("authorization") or ""
                bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
                if provided != api_key and bearer != api_key:
                    return JSONResponse({"detail": "unauthorized"}, status_code=401)
            response = await call_next(request)
            response.headers["X-Request-Id"] = request_id
            return response
        finally:
            reset_context()
