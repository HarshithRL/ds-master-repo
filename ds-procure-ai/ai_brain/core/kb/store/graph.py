"""Graph writer + entity resolution (W7).

Runs after all extraction so KPMG's two entities can be linked. Closed
edge vocabulary is enforced in Python *and* by `kb_edge.type` CHECK —
unknown types raise; they are never coerced. Uncited edges are dropped.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select, text

from ai_brain.core.kb.api.schemas import EntityMention
from shared.db.connection import mate_table_name, session_scope
from shared.db.models import KB_EDGE_TYPES, KB_NODE_TYPES, KbEdge, KbNode, QualityFlag, Vendor, utc_now_iso
from shared.logger_global import get_logger

log = get_logger(__name__)

EDGE_TYPES = frozenset(KB_EDGE_TYPES)
NODE_TYPES = frozenset(KB_NODE_TYPES)
EXPAND_AND_SUB = ("MEMBER_OF_CONSORTIUM", "SUBCONTRACTS_TO")
INDEPENDENCE_KIND = "independence_conflict"
MODEL_VERSION = "w7-resolver"
KPMG_GROUP_MARKERS = ("group", "belgium bv")
ResolverFn = Callable[["GraphProposal"], "GraphProposal"]


class ClosedVocabularyViolation(ValueError):
    def __init__(self, edge_type: str) -> None:
        self.edge_type = edge_type
        super().__init__(f"unknown kb_edge type {edge_type!r}; closed vocabulary, never coerce")


class GraphNode(BaseModel):
    type: str
    label: str
    registry_id: str | None = None
    canonical_key: str | None = None
    source_artifact_id: str | None = None
    source_page: int | None = None
    confidence: float = 1.0
    props: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    type: str
    src_key: str
    dst_key: str
    src_type: str = "LegalEntity"
    dst_type: str = "LegalEntity"
    source_artifact_id: str | None = None
    source_page: int | None = None
    confidence: float = 1.0
    props: dict[str, Any] = Field(default_factory=dict)


class GraphProposal(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


@dataclass
class GraphWriteReport:
    project_id: str
    nodes_upserted: int = 0
    edges_upserted: int = 0
    edges_dropped_uncited: int = 0
    independence_chains: list[dict[str, Any]] = field(default_factory=list)
    conflicts_flagged: int = 0


def canonical_key(mention: EntityMention | GraphNode) -> str:
    registry = (getattr(mention, "registry_id", None) or "").strip()
    if registry:
        return _slug(registry)
    key = getattr(mention, "canonical_key", None)
    if key:
        return _slug(str(key))
    return _slug(getattr(mention, "name", None) or getattr(mention, "label", "") or "")


def normalize_name(name: str) -> str:
    return " ".join((name or "").casefold().split())


def dedupe(
    mentions: Sequence[EntityMention],
    keys: Sequence[str] = ("registry_id", "normalized_name"),
) -> list[EntityMention]:
    """Registry id wins; same normalized name collapses unless registry ids differ."""
    by_registry: dict[str, EntityMention] = {}
    by_name: dict[str, EntityMention] = {}
    ordered: list[EntityMention] = []
    for mention in mentions:
        reg = (mention.registry_id or "").strip().casefold()
        name_key = normalize_name(mention.name)
        existing: EntityMention | None = None
        if "registry_id" in keys and reg:
            existing = by_registry.get(reg)
        if existing is None and "normalized_name" in keys and name_key:
            named = by_name.get(name_key)
            if named is not None:
                named_reg = (named.registry_id or "").strip().casefold()
                if not named_reg or not reg or named_reg == reg:
                    existing = named
        if existing is None:
            ordered.append(mention)
            if reg:
                by_registry[reg] = mention
            if name_key:
                by_name[name_key] = mention
            continue
        _merge_mention(existing, mention)
        if reg:
            by_registry[reg] = existing
    return ordered


def collect_entity_mentions(project_id: str) -> list[EntityMention]:
    """Vendor roster is the deterministic seed; extraction bundles add citations."""
    with session_scope() as session:
        vendors = session.scalars(select(Vendor).where(Vendor.project_id == project_id)).all()
        return [
            EntityMention(
                name=row.legal_entity or row.name,
                type="LegalEntity",
                registry_id=row.registry_id,
            )
            for row in vendors
        ]


def entity_resolver_agent(
    project_id: str,
    canon: Sequence[EntityMention],
    *,
    resolver: ResolverFn | None = None,
) -> GraphProposal:
    """Fast-model structured output in prod; tests inject `resolver`."""
    seed = _proposal_from_mentions(project_id, canon)
    if resolver is not None:
        return resolver(seed)
    return _deterministic_resolve(project_id, seed)


async def resolve_entities_and_write_graph(
    project_id: str,
    *,
    mentions: Sequence[EntityMention] | None = None,
    resolver: ResolverFn | None = None,
) -> GraphWriteReport:
    collected = list(mentions) if mentions is not None else collect_entity_mentions(project_id)
    canon = dedupe(collected, keys=["registry_id", "normalized_name"])
    proposals = entity_resolver_agent(project_id, canon, resolver=resolver)
    cited_edges, dropped = validate_and_filter_edges(proposals.edges)
    proposals = GraphProposal(nodes=list(proposals.nodes), edges=cited_edges)
    node_ids = upsert_nodes(project_id, proposals.nodes)
    edges_written = upsert_edges(project_id, proposals.edges, node_ids)
    chains, conflicts = detect_independence_conflicts(project_id)
    log.info(
        "graph write project_id={} nodes={} edges={} dropped_uncited={} conflicts={}",
        project_id,
        len(node_ids),
        edges_written,
        dropped,
        conflicts,
    )
    return GraphWriteReport(
        project_id=project_id,
        nodes_upserted=len(node_ids),
        edges_upserted=edges_written,
        edges_dropped_uncited=dropped,
        independence_chains=chains,
        conflicts_flagged=conflicts,
    )


def validate_and_filter_edges(edges: Sequence[GraphEdge]) -> tuple[list[GraphEdge], int]:
    for edge in edges:
        if edge.type not in EDGE_TYPES:
            raise ClosedVocabularyViolation(edge.type)
    cited = [
        edge
        for edge in edges
        if edge.source_artifact_id and edge.source_page is not None
    ]
    return cited, len(edges) - len(cited)


def upsert_nodes(project_id: str, nodes: Sequence[GraphNode]) -> dict[str, str]:
    """Keyed on (project, type, canonical key). Unknown types raise (CHECK)."""
    ids: dict[str, str] = {}
    with session_scope() as session:
        for node in nodes:
            if node.type not in NODE_TYPES:
                raise ClosedVocabularyViolation(node.type)
            key = node.canonical_key or _slug(node.registry_id or node.label)
            node_id = f"{project_id}:{node.type}:{key}"
            props = dict(node.props)
            if node.registry_id:
                props.setdefault("registry_id", node.registry_id)
            props["canonical_key"] = key
            row = session.get(KbNode, node_id)
            if row is None:
                session.add(
                    KbNode(
                        id=node_id,
                        project_id=project_id,
                        type=node.type,
                        label=node.label,
                        props=json.dumps(props, ensure_ascii=False),
                        source_artifact_id=node.source_artifact_id,
                        source_page=node.source_page,
                        confidence=node.confidence,
                        model_version=MODEL_VERSION,
                    )
                )
            else:
                row.label = node.label
                row.props = json.dumps(props, ensure_ascii=False)
                if node.source_artifact_id:
                    row.source_artifact_id = node.source_artifact_id
                if node.source_page is not None:
                    row.source_page = node.source_page
                row.confidence = node.confidence
                row.model_version = MODEL_VERSION
            ids[f"{node.type}:{key}"] = node_id
            ids[key] = node_id
    return ids


def upsert_edges(
    project_id: str,
    edges: Sequence[GraphEdge],
    node_ids: dict[str, str] | None = None,
) -> int:
    written = 0
    ids = node_ids or {}
    with session_scope() as session:
        for edge in edges:
            if edge.type not in EDGE_TYPES:
                raise ClosedVocabularyViolation(edge.type)
            if not (edge.source_artifact_id and edge.source_page is not None):
                continue
            src_id = _resolve_node_id(project_id, edge.src_type, edge.src_key, ids)
            dst_id = _resolve_node_id(project_id, edge.dst_type, edge.dst_key, ids)
            if (
                src_id is None
                or dst_id is None
                or session.get(KbNode, src_id) is None
                or session.get(KbNode, dst_id) is None
            ):
                log.info(
                    "skip edge type={} missing endpoint src={} dst={}",
                    edge.type,
                    edge.src_key,
                    edge.dst_key,
                )
                continue
            edge_id = f"{project_id}:{edge.type}:{src_id}:{dst_id}"
            row = session.get(KbEdge, edge_id)
            if row is None:
                session.add(
                    KbEdge(
                        id=edge_id,
                        project_id=project_id,
                        src=src_id,
                        dst=dst_id,
                        type=edge.type,
                        props=json.dumps(edge.props, ensure_ascii=False) if edge.props else None,
                        source_artifact_id=edge.source_artifact_id,
                        source_page=edge.source_page,
                        confidence=edge.confidence,
                        model_version=MODEL_VERSION,
                    )
                )
            else:
                row.source_artifact_id = edge.source_artifact_id
                row.source_page = edge.source_page
                row.confidence = edge.confidence
                row.model_version = MODEL_VERSION
            written += 1
    return written


def independence_cte() -> str:
    edge = mate_table_name("kb_edge")
    return f"""
WITH RECURSIVE chain AS (
  SELECT src, dst, type, 1 AS hop FROM {edge}
   WHERE project_id = :pid AND type IN ('MEMBER_OF_CONSORTIUM','SUBCONTRACTS_TO')
  UNION ALL
  SELECT e.src, e.dst, e.type, c.hop + 1
    FROM {edge} e JOIN chain c ON e.src = c.dst
   WHERE c.hop < 4 AND e.project_id = :pid
)
SELECT src, dst, type, hop FROM chain
 WHERE dst IN (SELECT dst FROM {edge} WHERE type = 'BIDS_ON' AND project_id = :pid)
"""


def detect_independence_conflicts(project_id: str) -> tuple[list[dict[str, Any]], int]:
    """Run the recursive CTE every build; bidder-as-subcontractor → CONFLICTS_WITH + flag."""
    with session_scope() as session:
        chain_rows = [
            dict(row)
            for row in session.execute(text(independence_cte()), {"pid": project_id}).mappings()
        ]
        edges = [
            dict(row)
            for row in session.execute(
                text(
                    "SELECT id, src, dst, type, source_artifact_id, source_page "
                    f"FROM {mate_table_name('kb_edge')} WHERE project_id = :pid"
                ),
                {"pid": project_id},
            ).mappings()
        ]

    bid_of = _bid_membership(edges)
    conflicts = 0
    for edge in edges:
        if edge["type"] != "SUBCONTRACTS_TO":
            continue
        src_bids = bid_of.get(edge["src"], set())
        dst_bids = bid_of.get(edge["dst"], set())
        if src_bids and dst_bids and src_bids.isdisjoint(dst_bids):
            conflicts += _write_conflict(project_id, edge)
    return chain_rows, conflicts


def _bid_membership(edges: Sequence[dict[str, Any]]) -> dict[str, set[str]]:
    """Map node → bid ids via MEMBER_OF_CONSORTIUM (undirected) and BIDS_ON src."""
    bids: dict[str, set[str]] = {}
    consortium: list[tuple[str, str]] = []
    for edge in edges:
        if edge["type"] == "BIDS_ON":
            bids.setdefault(edge["src"], set()).add(edge["src"])
            bids.setdefault(edge["dst"], set()).add(edge["src"])
        elif edge["type"] == "MEMBER_OF_CONSORTIUM":
            consortium.append((edge["src"], edge["dst"]))
            bids.setdefault(edge["dst"], set()).add(edge["dst"])
            bids.setdefault(edge["src"], set()).add(edge["dst"])
    return bids


def _write_conflict(project_id: str, sub_edge: dict[str, Any]) -> int:
    artifact_id = sub_edge.get("source_artifact_id")
    page = sub_edge.get("source_page")
    if not (artifact_id and page is not None):
        return 0
    conflict = GraphEdge(
        type="CONFLICTS_WITH",
        src_key=edge_key_from_id(sub_edge["src"]),
        dst_key=edge_key_from_id(sub_edge["dst"]),
        src_type=_type_from_id(sub_edge["src"]),
        dst_type=_type_from_id(sub_edge["dst"]),
        source_artifact_id=str(artifact_id),
        source_page=int(page),
        props={"via": "SUBCONTRACTS_TO"},
    )
    upsert_edges(
        project_id,
        [conflict],
        {
            f"{conflict.src_type}:{conflict.src_key}": sub_edge["src"],
            f"{conflict.dst_type}:{conflict.dst_key}": sub_edge["dst"],
            conflict.src_key: sub_edge["src"],
            conflict.dst_key: sub_edge["dst"],
        },
    )
    now = utc_now_iso()
    with session_scope() as session:
        session.add(
            QualityFlag(
                id=str(uuid.uuid4()),
                project_id=project_id,
                artifact_id=str(artifact_id),
                kind=INDEPENDENCE_KIND,
                detail=(
                    f"bidder {sub_edge['src']} also SUBCONTRACTS_TO competing "
                    f"{sub_edge['dst']}"
                ),
                severity="high",
                created_at=now,
            )
        )
    return 1


def edge_key_from_id(node_id: str) -> str:
    return node_id.rsplit(":", 1)[-1]


def _type_from_id(node_id: str) -> str:
    parts = node_id.split(":")
    return parts[1] if len(parts) >= 3 else "LegalEntity"


def _resolve_node_id(
    project_id: str,
    node_type: str,
    key: str,
    ids: dict[str, str],
) -> str | None:
    slug = _slug(key)
    for candidate in (
        f"{node_type}:{slug}",
        slug,
        key,
        f"{node_type}:{key}",
        f"{project_id}:{node_type}:{slug}",
    ):
        if candidate in ids:
            return ids[candidate]
    return f"{project_id}:{node_type}:{slug}"


def _proposal_from_mentions(project_id: str, canon: Sequence[EntityMention]) -> GraphProposal:
    nodes: list[GraphNode] = []
    for mention in canon:
        key = canonical_key(mention)
        if not key:
            continue
        nodes.append(
            GraphNode(
                type=mention.type if mention.type in NODE_TYPES else "LegalEntity",
                label=mention.name,
                registry_id=mention.registry_id,
                canonical_key=key,
                source_artifact_id=mention.artifact_id,
                source_page=mention.page,
            )
        )
    return GraphProposal(nodes=nodes, edges=[])


def _deterministic_resolve(project_id: str, seed: GraphProposal) -> GraphProposal:
    """No-LLM fallback: consortium from shared artifact, KPMG PARENT_OF heuristic."""
    nodes = list(seed.nodes)
    edges: list[GraphEdge] = list(seed.edges)
    by_artifact: dict[str, list[GraphNode]] = {}
    for node in nodes:
        if node.type == "LegalEntity" and node.source_artifact_id:
            by_artifact.setdefault(node.source_artifact_id, []).append(node)

    for artifact_id, members in by_artifact.items():
        if len(members) < 2:
            continue
        bid_label = " / ".join(n.label for n in members)
        bid_key = _slug(bid_label) or _slug(artifact_id)
        page = next((n.source_page for n in members if n.source_page is not None), None)
        bid = GraphNode(
            type="Bid",
            label=bid_label,
            canonical_key=bid_key,
            source_artifact_id=artifact_id,
            source_page=page,
            props={"bid_id": bid_key},
        )
        nodes.append(bid)
        for member in members:
            if member.source_page is None:
                continue
            edges.append(
                GraphEdge(
                    type="MEMBER_OF_CONSORTIUM",
                    src_key=member.canonical_key or _slug(member.label),
                    dst_key=bid_key,
                    src_type="LegalEntity",
                    dst_type="Bid",
                    source_artifact_id=member.source_artifact_id,
                    source_page=member.source_page,
                )
            )

    legal = [n for n in nodes if n.type == "LegalEntity"]
    parent, child = _kpmg_parent_pair(legal)
    if parent is not None and child is not None:
        page = parent.source_page if parent.source_page is not None else child.source_page
        art = parent.source_artifact_id or child.source_artifact_id
        if art and page is not None:
            edges.append(
                GraphEdge(
                    type="PARENT_OF",
                    src_key=parent.canonical_key or _slug(parent.label),
                    dst_key=child.canonical_key or _slug(child.label),
                    src_type="LegalEntity",
                    dst_type="LegalEntity",
                    source_artifact_id=art,
                    source_page=page,
                )
            )
    return GraphProposal(nodes=nodes, edges=edges)


def _kpmg_parent_pair(nodes: Sequence[GraphNode]) -> tuple[GraphNode | None, GraphNode | None]:
    kpmg = [n for n in nodes if "kpmg" in normalize_name(n.label)]
    if len(kpmg) < 2:
        return None, None
    parents = [n for n in kpmg if any(m in normalize_name(n.label) for m in KPMG_GROUP_MARKERS)]
    children = [n for n in kpmg if n not in parents]
    if not parents:
        parents = [kpmg[0]]
        children = kpmg[1:]
    if not children:
        return None, None
    return parents[0], children[0]


def _merge_mention(existing: EntityMention, incoming: EntityMention) -> None:
    if not existing.registry_id and incoming.registry_id:
        existing.registry_id = incoming.registry_id
    if not existing.artifact_id and incoming.artifact_id:
        existing.artifact_id = incoming.artifact_id
        existing.page = incoming.page
    elif existing.page is None and incoming.page is not None:
        existing.page = incoming.page


def _slug(value: str | None) -> str:
    chars: list[str] = []
    prev_dash = False
    for char in (value or "").strip().lower():
        if char.isalnum():
            chars.append(char)
            prev_dash = False
        elif not prev_dash:
            chars.append("-")
            prev_dash = True
    return "".join(chars).strip("-")
