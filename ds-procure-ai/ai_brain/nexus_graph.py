"""Nexus graph. Procurement subgraph is gated by capability or mainagent / deepagent flags."""

from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from ai_brain.core.procurement_ai.procura_graph import (
    ProcurementState,
    build_procura_ai,
    merge_dicts,
    procurement_on,
)


class NexesState(TypedDict):
    request: str
    project_id: str
    capability: str
    procurement: Annotated[ProcurementState, merge_dicts]
    route: str
    messages: Annotated[list, add_messages]


def choose_path(state: NexesState) -> Literal["procurement", "skip"]:
    return "procurement" if procurement_on(state) else "skip"


def skip_node(state: NexesState) -> dict:
    return {
        "route": "skip",
        "procurement": {"main_agent": "", "deep_agent": ""},
    }


def mark_procurement_route(state: NexesState) -> dict:
    return {"route": "procurement"}


def build_nexes_graph(*, checkpointer=None, store=None):
    g = StateGraph(NexesState)
    g.add_node("procurement", build_procura_ai())
    g.add_node("mark_procurement_route", mark_procurement_route)
    g.add_node("skip", skip_node)
    g.add_conditional_edges(
        START,
        choose_path,
        {"procurement": "procurement", "skip": "skip"},
    )
    g.add_edge("procurement", "mark_procurement_route")
    g.add_edge("mark_procurement_route", END)
    g.add_edge("skip", END)
    kwargs: dict = {"name": "nexus"}
    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer
    if store is not None:
        kwargs["store"] = store
    return g.compile(**kwargs)


# Aliases. Flask and runtime still import the Nexes* names.
NexusState = NexesState
build_nexus_graph = build_nexes_graph
