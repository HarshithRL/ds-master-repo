from __future__ import annotations

import operator
from typing import Annotated, Literal, NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from ai_brain.core.procurement_ai.capabilities import (
    COMPARE_XLSX,
    KB_BUILD,
    STEERCO_PPT,
    capability_from_state,
)


def merge_dicts(left: dict | None, right: dict | None) -> dict:
    """Deep-merge nested control/output dicts so node updates do not wipe flags."""
    left = dict(left or {})
    right = dict(right or {})
    out = left
    for key, value in right.items():
        existing = out.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            out[key] = merge_dicts(existing, value)
        else:
            out[key] = value
    return out


class ProcurementState(TypedDict, total=False):
    mainagent: bool
    deepagent: bool
    capability: str
    project_id: str
    main_agent: str
    deep_agent: str
    compare_xlsx: str
    steerco_ppt: str
    xlsx_status: str
    ppt_status: str
    xlsx_href: str
    ppt_href: str


class ProcuraState(TypedDict):
    request: str
    project_id: str
    capability: str
    procurement: Annotated[ProcurementState, merge_dicts]
    messages: Annotated[list, add_messages]
    kb_bundles: NotRequired[Annotated[list, operator.add]]
    file_results: NotRequired[Annotated[list, operator.add]]
    requirements_ready: NotRequired[bool]


def _procurement(state: dict) -> dict:
    return state.get("procurement") or {}


def mainagent_on(state: dict) -> bool:
    return bool(_procurement(state).get("mainagent"))


def deepagent_on(state: dict) -> bool:
    return bool(_procurement(state).get("deepagent"))


def procurement_on(state: dict) -> bool:
    if capability_from_state(state):
        return True
    return mainagent_on(state) or deepagent_on(state)


def after_start(
    state: ProcuraState,
) -> Literal["main_agent", "skip_main", "compare_xlsx", "steerco_ppt", "extract_requirements", "ingest"]:
    capability = capability_from_state(state)
    if capability == COMPARE_XLSX:
        return "compare_xlsx"
    if capability == STEERCO_PPT:
        return "steerco_ppt"
    if capability == KB_BUILD:
        return "extract_requirements"
    from ai_brain.core.procurement_ai.file_ingest import pending_files

    project_id = str(state.get("project_id") or "").strip()
    if pending_files(project_id):
        return "ingest"
    return "main_agent" if mainagent_on(state) else "skip_main"


def after_main(state: ProcuraState) -> Literal["deepagent", "skip_deepagent"]:
    return "deepagent" if deepagent_on(state) else "skip_deepagent"


def skip_main(state: ProcuraState) -> dict:
    return {"procurement": {"main_agent": ""}}


def skip_deepagent(state: ProcuraState) -> dict:
    return {"procurement": {"deep_agent": ""}}


def build_procura_ai(*, checkpointer=None, store=None):
    from ai_brain.core.kb.pipeline import (
        analyze_bid,
        audit_kb,
        extract_requirements,
        fill_overview,
        fill_requirements,
        fill_vendors,
        plan_kb_build,
        plan_publish,
    )
    from ai_brain.core.procurement_ai.subagents.compare_xlsx import compare_xlsx
    from ai_brain.core.procurement_ai.subagents.deepagents import deepagent
    from ai_brain.core.procurement_ai.subagents.main_agent import main_agent
    from ai_brain.core.procurement_ai.subagents.steerco_ppt import steerco_ppt
    from ai_brain.core.procurement_ai.file_ingest import (
        chunk_one,
        index_docs,
        join_docs,
        parse_one,
        route_new_files,
    )

    def ingest_mark(state: ProcuraState) -> dict:
        return {"route": "ingest"}

    def after_index(state: ProcuraState) -> Literal["main_agent", "skip_main"]:
        return "main_agent" if mainagent_on(state) else "skip_main"

    def route_ingest(state: ProcuraState):
        routed = route_new_files(state)
        if routed == "assistant":
            return after_index(state)
        return routed

    g = StateGraph(ProcuraState)
    g.add_node("main_agent", main_agent)
    g.add_node("skip_main", skip_main)
    g.add_node("deepagent", deepagent)
    g.add_node("skip_deepagent", skip_deepagent)
    g.add_node("compare_xlsx", compare_xlsx)
    g.add_node("steerco_ppt", steerco_ppt)
    g.add_node("ingest", ingest_mark)
    g.add_node("parse_one", parse_one)
    g.add_node("chunk_one", chunk_one)
    g.add_node("join_docs", join_docs)
    g.add_node("index_docs", index_docs)
    g.add_node("extract_requirements", extract_requirements)
    g.add_node("analyze_bid", analyze_bid)
    g.add_node("audit_kb", audit_kb)
    g.add_node("fill_overview", fill_overview)
    g.add_node("fill_requirements", fill_requirements)
    g.add_node("fill_vendors", fill_vendors)
    g.add_conditional_edges(
        START,
        after_start,
        {
            "main_agent": "main_agent",
            "skip_main": "skip_main",
            "compare_xlsx": "compare_xlsx",
            "steerco_ppt": "steerco_ppt",
            "extract_requirements": "extract_requirements",
            "ingest": "ingest",
        },
    )
    g.add_conditional_edges(
        "ingest",
        route_ingest,
        ["parse_one", "main_agent", "skip_main"],
    )
    g.add_edge("parse_one", "chunk_one")
    g.add_edge("chunk_one", "join_docs")
    g.add_edge("join_docs", "index_docs")
    g.add_conditional_edges("index_docs", after_index, {"main_agent": "main_agent", "skip_main": "skip_main"})
    deepagent_next = {"deepagent": "deepagent", "skip_deepagent": "skip_deepagent"}
    g.add_conditional_edges("main_agent", after_main, deepagent_next)
    g.add_conditional_edges("skip_main", after_main, deepagent_next)
    g.add_conditional_edges(
        "extract_requirements",
        plan_kb_build,
        ["analyze_bid", "audit_kb"],
    )
    g.add_edge("analyze_bid", "audit_kb")
    g.add_conditional_edges(
        "audit_kb",
        plan_publish,
        ["fill_overview", "fill_requirements", "fill_vendors"],
    )
    g.add_edge("fill_overview", END)
    g.add_edge("fill_requirements", END)
    g.add_edge("fill_vendors", END)
    g.add_edge("deepagent", END)
    g.add_edge("skip_deepagent", END)
    g.add_edge("compare_xlsx", END)
    g.add_edge("steerco_ppt", END)
    kwargs: dict = {"name": "procura"}
    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer
    if store is not None:
        kwargs["store"] = store
    return g.compile(**kwargs)
