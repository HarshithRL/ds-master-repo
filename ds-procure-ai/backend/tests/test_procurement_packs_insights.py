"""Fast, coalesced insight retrieval regression tests."""

from __future__ import annotations

from services import procurement_packs


def _reset_cache():
    procurement_packs._INSIGHT_CACHE.clear()
    procurement_packs._INSIGHT_IN_FLIGHT.clear()


def test_insights_cache_avoids_repeat_brain_calls(monkeypatch):
    _reset_cache()
    project = object()
    calls = []
    monkeypatch.setattr(
        procurement_packs.project_repo, "get_for_owner_or_none", lambda *_: project
    )

    def brain(_path):
        calls.append(_path)
        return {"project_id": "project-1", "insights": []}

    monkeypatch.setattr(procurement_packs, "_brain_get", brain)
    first = procurement_packs.insights_for_owner("project-1", "owner-1")
    second = procurement_packs.insights_for_owner("project-1", "owner-1")

    assert first == second
    assert calls == ["/v1/projects/project-1/insights"]


def test_insights_timeout_uses_local_payload(monkeypatch):
    _reset_cache()
    project = object()
    monkeypatch.setattr(
        procurement_packs.project_repo, "get_for_owner_or_none", lambda *_: project
    )
    monkeypatch.setattr(procurement_packs, "_brain_get", lambda *_: (_ for _ in ()).throw(TimeoutError()))
    monkeypatch.setattr(procurement_packs, "_build_local_insights", lambda *_: {"project_id": "p", "fallback": True})

    assert procurement_packs.insights_for_owner("p", "owner") == {"project_id": "p", "fallback": True}
