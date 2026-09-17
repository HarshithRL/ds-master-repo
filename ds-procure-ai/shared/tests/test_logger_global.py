"""Flat JSON / pretty sinks for Mate logger_global (no live Databricks)."""

from __future__ import annotations

import json
import logging

import pytest

from shared.logger_global import controller as ctrl
from shared.logger_global.formatters import dump_json_record

_LOG_ENV = (
    "MATE_ENV",
    "MATE_LOG_FORMAT",
    "MATE_LOG_LEVEL",
    "MATE_LOG_DIR",
    "MATE_STDLIB_LOG_LEVEL",
    "DATABRICKS_APP_NAME",
    "DATABRICKS_CLIENT_ID",
    "DATABRICKS_CLIENT_SECRET",
)


@pytest.fixture
def isolated_logging(tmp_path, monkeypatch):
    for name in _LOG_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MATE_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("MATE_ENV", "dev")
    ctrl.reset_logging()
    yield tmp_path
    ctrl.reset_logging()


def _stderr_json_lines(err: str) -> list[dict]:
    rows = []
    for line in err.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        rows.append(json.loads(stripped))
    return rows


def test_flat_json_line_has_top_level_fields(isolated_logging, capsys, monkeypatch):
    monkeypatch.setenv("MATE_LOG_FORMAT", "json")
    ctrl.setup_logging(service="backend")
    ctrl.get_logger("unit.test").info("hello matrix")
    rows = _stderr_json_lines(capsys.readouterr().err)
    assert rows
    payload = next(row for row in rows if row.get("message") == "hello matrix")
    assert payload["level"] == "INFO"
    assert payload["service"] == "backend"
    assert payload["module"] == "unit.test"
    assert "record" not in payload
    assert "text" not in payload


def test_prod_skips_file_sinks(isolated_logging, monkeypatch):
    monkeypatch.setenv("MATE_ENV", "prod")
    ctrl.setup_logging(service="backend")
    ctrl.get_logger("unit.test").info("no files")
    assert list(isolated_logging.iterdir()) == []


def test_apps_runtime_defaults_json_and_skips_files(isolated_logging, monkeypatch, capsys):
    monkeypatch.setenv("DATABRICKS_APP_NAME", "ds-procure-ai")
    monkeypatch.delenv("MATE_ENV", raising=False)
    ctrl.setup_logging(service="ai_brain")
    ctrl.get_logger("unit.apps").warning("apps line")
    rows = _stderr_json_lines(capsys.readouterr().err)
    payload = next(row for row in rows if row.get("message") == "apps line")
    assert payload["service"] == "ai_brain"
    assert payload["level"] == "WARNING"
    assert list(isolated_logging.iterdir()) == []


def test_pretty_local_path(isolated_logging, capsys):
    ctrl.setup_logging(service="backend")
    ctrl.get_logger("unit.pretty").info("pretty line")
    err = capsys.readouterr().err
    assert "pretty line" in err
    assert "backend" in err
    assert "unit.pretty" in err
    assert not any(line.strip().startswith("{") and "pretty line" in line for line in err.splitlines())
    assert (isolated_logging / "backend.log").exists()


def test_explicit_pretty_in_prod_is_not_colorized_json(isolated_logging, monkeypatch, capsys):
    monkeypatch.setenv("MATE_ENV", "prod")
    monkeypatch.setenv("MATE_LOG_FORMAT", "pretty")
    ctrl.setup_logging(service="backend")
    ctrl.get_logger("unit.prodpretty").info("keep pretty")
    err = capsys.readouterr().err
    assert "keep pretty" in err
    assert "\x1b[" not in err


def test_stdlib_intercept_sets_module(isolated_logging, capsys, monkeypatch):
    monkeypatch.setenv("MATE_STDLIB_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("MATE_LOG_FORMAT", "json")
    ctrl.setup_logging(service="ai_brain")
    logging.getLogger("uvicorn.access").warning("GET /health 200")
    rows = _stderr_json_lines(capsys.readouterr().err)
    payload = next(row for row in rows if "GET /health 200" in row.get("message", ""))
    assert payload["module"] == "uvicorn.access"
    assert payload["service"] == "ai_brain"


def test_dump_json_record_schema():
    class _Level:
        name = "ERROR"

    line = dump_json_record(
        {
            "time": "2026-09-17T12:00:00.000+00:00",
            "level": _Level(),
            "message": "boom",
            "extra": {
                "service": "backend",
                "module": "packs",
                "request_id": "r1",
                "workflow": "compare",
                "project_id": "p1",
            },
        }
    )
    payload = json.loads(line)
    assert payload == {
        "time": "2026-09-17T12:00:00.000+00:00",
        "level": "ERROR",
        "service": "backend",
        "module": "packs",
        "request_id": "r1",
        "workflow": "compare",
        "project_id": "p1",
        "message": "boom",
    }
