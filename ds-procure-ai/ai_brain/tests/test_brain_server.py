"""AI Brain AgentServer tests (in-memory graph, stubbed agents, no Databricks)."""

from __future__ import annotations

import json
import os

os.environ.setdefault("BRAIN_CHECKPOINT_BACKEND", "memory")
os.environ.setdefault("BRAIN_STORE_BACKEND", "memory")
os.environ.setdefault("MLFLOW_EXPERIMENT_NAME", "ai_brain_tests")
os.environ.setdefault("MLFLOW_ENABLE_ASYNC_LOGGING", "false")

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def stub_agents(monkeypatch):
    captured: dict = {}

    async def main_agent(state, config=None):
        captured["state"] = state
        captured["config"] = config
        return {"procurement": {"main_agent": "main-ok"}}

    async def deepagent(state, config=None):
        return {"procurement": {"deep_agent": "deep-ok"}}

    import importlib

    main_mod = importlib.import_module("ai_brain.core.procurement_ai.subagents.main_agent")
    deep_mod = importlib.import_module("ai_brain.core.procurement_ai.subagents.deepagents")
    monkeypatch.setattr(main_mod, "main_agent", main_agent)
    monkeypatch.setattr(deep_mod, "deepagent", deepagent)
    monkeypatch.setenv("BRAIN_CHECKPOINT_BACKEND", "memory")
    monkeypatch.setenv("BRAIN_STORE_BACKEND", "memory")
    return captured


@pytest.fixture
def client(stub_agents):
    from ai_brain.brain_server import app

    with TestClient(app) as test_client:
        yield test_client


def test_health(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json().get("status") in {"healthy", "ok"}


def test_ready(client: TestClient):
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "ai_brain"
    assert body["graph"] is True


def test_invoke_skip_route(client: TestClient):
    response = client.post(
        "/invoke",
        json={
            "request": "hello",
            "procurement": {"mainagent": False, "deepagent": False},
            "thread_id": "thread-skip",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "skip"
    assert body["thread_id"] == "thread-skip"
    assert body["procurement"]["main_agent"] == ""
    assert body["procurement"]["deep_agent"] == ""


def test_invoke_main_agent_flag(client: TestClient):
    response = client.post(
        "/invoke",
        json={
            "request": "compare vendors",
            "procurement": {"mainagent": True, "deepagent": False},
            "thread_id": "thread-main",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "procurement"
    assert body["procurement"]["main_agent"] == "main-ok"


def test_invoke_forwards_project_id_and_user(client: TestClient, stub_agents):
    response = client.post(
        "/invoke",
        json={
            "request": "compare vendors",
            "procurement": {"mainagent": True, "deepagent": False, "project_id": "proj-uuid"},
            "thread_id": "proj-uuid",
            "project_id": "proj-uuid",
        },
        headers={"x-user-id": "owner-9"},
    )
    assert response.status_code == 200
    assert stub_agents["state"]["project_id"] == "proj-uuid"
    assert stub_agents["state"]["procurement"]["project_id"] == "proj-uuid"
    assert stub_agents["config"]["configurable"]["user_id"] == "owner-9"


def test_invocations_forwards_user_id_from_custom_inputs(client: TestClient, stub_agents):
    response = client.post(
        "/invocations",
        json={
            "input": [{"role": "user", "content": "hello", "type": "message"}],
            "custom_inputs": {
                "request": "hello",
                "procurement": {
                    "mainagent": True,
                    "deepagent": False,
                    "project_id": "proj-stream",
                },
                "thread_id": "proj-stream",
                "user_id": "owner-stream",
            },
            "stream": True,
        },
    )
    assert response.status_code == 200
    assert stub_agents["state"]["project_id"] == "proj-stream"
    assert stub_agents["config"]["configurable"]["user_id"] == "owner-stream"


def test_invoke_requires_request(client: TestClient):
    response = client.post("/invoke", json={"request": "  ", "procurement": {}})
    assert response.status_code == 400


def test_invocations_stream(client: TestClient):
    response = client.post(
        "/invocations",
        json={
            "input": [{"role": "user", "content": "hello", "type": "message"}],
            "custom_inputs": {
                "request": "hello",
                "procurement": {"mainagent": True, "deepagent": True},
                "thread_id": "thread-stream",
            },
            "stream": True,
        },
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    payloads = []
    for line in response.text.splitlines():
        if not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            continue
        payloads.append(json.loads(data))
    types = [item.get("type") for item in payloads]
    assert "response.output_item.done" in types


def test_thread_state_after_invoke(client: TestClient):
    client.post(
        "/invoke",
        json={
            "request": "hello",
            "procurement": {},
            "thread_id": "thread-state",
        },
    )
    response = client.get("/v1/threads/thread-state/state")
    assert response.status_code == 200
    body = response.json()
    assert body["values"]["route"] == "skip"


def test_thread_history(client: TestClient):
    client.post(
        "/invoke",
        json={"request": "hello", "procurement": {}, "thread_id": "thread-hist"},
    )
    response = client.get("/v1/threads/thread-hist/history")
    assert response.status_code == 200
    assert len(response.json()["history"]) >= 1


def test_unknown_thread_404(client: TestClient):
    response = client.get("/v1/threads/does-not-exist/state")
    assert response.status_code == 404


def test_root_ok(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "ai_brain"


def test_project_insights_200(client: TestClient, monkeypatch):
    class Project:
        id = "proj-demo"
        code = "PR-100"
        name = "SWIFT CSP"
        business_process = "Indirect"
        category = "SWIFT CSCF"
        description = "days"

    monkeypatch.setattr(
        "ai_brain.server.project_routes.load_context",
        lambda _pid: (Project(), [], []),
    )
    response = client.get("/v1/projects/proj-demo/insights")
    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == "proj-demo"
    assert body["process_type"] == "indirect_it_services"


def test_project_insights_404(client: TestClient, monkeypatch):
    monkeypatch.setattr(
        "ai_brain.server.project_routes.load_context",
        lambda _pid: (None, [], []),
    )
    response = client.get("/v1/projects/missing/insights")
    assert response.status_code == 404


def test_project_packs_200(client: TestClient, monkeypatch):
    class Project:
        id = "proj-demo"

    monkeypatch.setattr(
        "ai_brain.server.project_routes.load_project",
        lambda _pid: Project(),
    )
    monkeypatch.setattr(
        "ai_brain.server.project_routes.pack_store.read_status",
        lambda _pid: {"xlsx": {"status": "idle"}, "ppt": {"status": "idle"}},
    )
    response = client.get("/v1/projects/proj-demo/packs")
    assert response.status_code == 200
    assert response.json()["xlsx"]["status"] == "idle"


def test_project_run_bad_capability(client: TestClient):
    response = client.post(
        "/v1/projects/proj-demo/runs",
        json={"capability": "nope", "message": "x", "thread_id": "t1"},
    )
    assert response.status_code == 400


def test_thread_update(client: TestClient):
    client.post(
        "/invoke",
        json={"request": "hello", "procurement": {}, "thread_id": "thread-upd"},
    )
    response = client.post(
        "/v1/threads/thread-upd/update",
        json={"values": {"route": "patched"}},
    )
    assert response.status_code == 200
    state = client.get("/v1/threads/thread-upd/state")
    assert state.json()["values"]["route"] == "patched"


def test_agent_nodes_receive_runnable_config():
    """LangGraph only injects ``config`` when the annotation matches literally."""
    from langgraph._internal._runnable import RunnableCallable

    from ai_brain.core.procurement_ai.subagents.deepagents import deepagent
    from ai_brain.core.procurement_ai.subagents.main_agent import main_agent

    for node in (main_agent, deepagent):
        wrapped = RunnableCallable(None, node)
        assert "config" in wrapped.func_accepts, f"{node.__name__} would not receive config"


def test_user_id_from_request_prefers_custom_inputs():
    from mlflow.types.responses import ResponsesAgentRequest

    from ai_brain.server.agent import user_id_from_request

    request = ResponsesAgentRequest(
        input=[{"role": "user", "content": "hi", "type": "message"}],
        custom_inputs={"user_id": "owner-9"},
    )
    assert user_id_from_request(request) == "owner-9"


def test_responses_custom_inputs_keeps_project_id():
    from ai_brain.server.routes import _responses_custom_inputs

    custom = _responses_custom_inputs(
        text="hello",
        procurement={"mainagent": True, "deepagent": False, "project_id": "proj-1"},
        thread_id="proj-1",
        user_id="owner-1",
    )
    assert custom["procurement"]["project_id"] == "proj-1"
    assert custom["procurement"]["mainagent"] is True
    assert custom["user_id"] == "owner-1"


def test_graph_config_attaches_mlflow_langchain_tracer():
    from mlflow.langchain.langchain_tracer import MlflowLangchainTracer

    from ai_brain.server.request import graph_config

    config = graph_config("thread-cfg")
    assert config["metadata"]["mlflow.trace.session"] == "thread-cfg"
    assert config["tags"] == ["ai_brain", "nexus"]
    assert any(isinstance(cb, MlflowLangchainTracer) for cb in config["callbacks"])
    tracer = next(cb for cb in config["callbacks"] if isinstance(cb, MlflowLangchainTracer))
    assert tracer.run_inline is True


def test_mlflow_traces_after_invoke(client: TestClient):
    import mlflow

    client.post(
        "/invoke",
        json={
            "request": "trace me",
            "procurement": {"mainagent": True},
            "thread_id": "thread-trace",
        },
    )
    mlflow.flush_trace_async_logging()
    experiment = mlflow.get_experiment_by_name("ai_brain_tests")
    assert experiment is not None
    traces = mlflow.search_traces(
        locations=[experiment.experiment_id],
        filter_string="metadata.`mlflow.trace.session` = 'thread-trace'",
    )
    assert len(traces) > 0
    trace = mlflow.get_trace(traces.iloc[0].trace_id)
    names = [span.name for span in trace.data.spans]
    assert names
    assert any(
        "non_streaming" in name or "nexus_graph" in name or "streaming" in name
        for name in names
    )
    info = trace.info
    session = (info.trace_metadata or {}).get("mlflow.trace.session")
    assert session == "thread-trace"
