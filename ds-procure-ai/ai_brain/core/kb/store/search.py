"""Hybrid KB retrieval: graph-expand → filter → BM25+vector → RRF → neighbour expand.

Chat-path only; extraction never retrieves. Sqlite runs lexical + optional
JSON vectors; Lakebase tsvector/pgvector SQL is the production branch.
"""

from __future__ import annotations

import json
import math
import re
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from sqlalchemy import bindparam, text

from ai_brain.core.kb.store.embed import embed_query, load_embeddings
from shared.db.connection import session_scope
from shared.logger_global import get_logger

log = get_logger(__name__)

RRF_K0 = 60
RETRIEVER_LIMIT = 25
EXPAND_EDGE_TYPES = frozenset({"MEMBER_OF_CONSORTIUM", "PARENT_OF"})
TRIGRAM_THRESHOLD = 0.25
_TOKEN = re.compile(r"[a-z0-9]{2,}")
_STOP = frozenset(
    {
        "the",
        "and",
        "for",
        "this",
        "that",
        "with",
        "from",
        "about",
        "what",
        "who",
        "how",
        "are",
        "was",
        "of",
        "to",
        "in",
        "on",
        "a",
        "an",
    }
)

_project_id: ContextVar[str | None] = ContextVar("kb_search_project_id", default=None)


@dataclass(frozen=True)
class RankedHit:
    chunk_id: str
    score: float


@dataclass
class ChunkHit:
    chunk_id: str
    artifact_id: str
    original_name: str
    page: int | None
    heading: str
    ordinal: int
    text: str
    score: float = 0.0
    neighbour: bool = False
    locator: str = ""


def set_current_project_id(project_id: str | None) -> None:
    _project_id.set(project_id)


def current_project_id() -> str:
    pid = (_project_id.get() or "").strip()
    if not pid:
        raise RuntimeError("current_project_id is not set")
    return pid


def rrf(
    rankings: Sequence[Sequence[tuple[str, float] | str]],
    k0: int = RRF_K0,
) -> list[RankedHit]:
    """Reciprocal rank fusion: score = sum 1/(k0+rank) over ranked lists.

    `rankings` are already ordered best-first. Rank is 1-based. Ties break
    on chunk_id so fusion is deterministic for a fixed candidate set.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            chunk_id = item[0] if isinstance(item, tuple) else item
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k0 + rank)
    return [
        RankedHit(chunk_id=chunk_id, score=score)
        for chunk_id, score in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def graph_expand_entities(project_id: str, query: str) -> list[str]:
    """Trigram-match query terms to `kb_node.label`, hop MEMBER_OF_CONSORTIUM
    / PARENT_OF (1–2 hops, undirected), return candidate artifact ids.

    Empty match → no artifact pre-filter (search the whole project).
    """
    with session_scope() as session:
        nodes = [
            dict(row)
            for row in session.execute(
                text(
                    "SELECT id, type, label, props, source_artifact_id "
                    "FROM kb_node WHERE project_id = :pid"
                ),
                {"pid": project_id},
            ).mappings()
        ]
        edges = [
            dict(row)
            for row in session.execute(
                text(
                    "SELECT src, dst, type FROM kb_edge "
                    "WHERE project_id = :pid AND type IN ('MEMBER_OF_CONSORTIUM','PARENT_OF')"
                ),
                {"pid": project_id},
            ).mappings()
        ]

    matched_ids = {n["id"] for n in nodes if _label_matches(query, n["label"] or "")}
    if not matched_ids:
        return []

    frontier = set(matched_ids)
    seen = set(matched_ids)
    for _hop in range(2):
        nxt: set[str] = set()
        for edge in edges:
            if edge["type"] not in EXPAND_EDGE_TYPES:
                continue
            if edge["src"] in frontier and edge["dst"] not in seen:
                nxt.add(edge["dst"])
            if edge["dst"] in frontier and edge["src"] not in seen:
                nxt.add(edge["src"])
        seen |= nxt
        frontier = nxt
        if not nxt:
            break

    by_id = {n["id"]: n for n in nodes}
    expanded = [by_id[i] for i in seen if i in by_id]
    artifact_ids: set[str] = set()
    bid_keys: set[str] = set()
    for node in expanded:
        src_art = node.get("source_artifact_id")
        if src_art:
            artifact_ids.add(str(src_art))
        props = _props(node.get("props"))
        if node["type"] == "Bid":
            key = str(props.get("bid_id") or _id_tail(node["id"]))
            if key:
                bid_keys.add(key)
        if node["type"] == "Artifact":
            aid = str(props.get("artifact_id") or src_art or _id_tail(node["id"]))
            if aid:
                artifact_ids.add(aid)

    if bid_keys:
        stmt = text(
            "SELECT id FROM artifact WHERE project_id = :pid AND vendor_id IN :bids"
        ).bindparams(bindparam("bids", expanding=True))
        with session_scope() as session:
            rows = session.execute(stmt, {"pid": project_id, "bids": list(bid_keys)}).all()
            artifact_ids.update(r[0] for r in rows)

    return sorted(artifact_ids)


def search_kb(
    query: str,
    vendor: str | None = None,
    doc_role: str | None = None,
    chunk_type: str | None = None,
    k: int = 8,
    *,
    project_id: str | None = None,
    embed_fn: Any | None = None,
) -> str:
    """Search the project knowledge base. Filters: vendor, doc_role
    (rfp|proposal|pricing|registry|csr), chunk_type (text|table).
    Returns chunks with [artifact / page / heading] provenance headers.
    """
    pid = (project_id or current_project_id()).strip()
    artifact_ids = graph_expand_entities(pid, query)
    chunks = _load_filtered_chunks(pid, vendor, doc_role, chunk_type, artifact_ids)
    bm25 = _lexical_rank(query, chunks)[:RETRIEVER_LIMIT]
    vec = _vector_rank(pid, query, chunks, embed_fn=embed_fn)[:RETRIEVER_LIMIT]
    fused = rrf([bm25, vec], k0=RRF_K0)
    by_id = {c.chunk_id: c for c in chunks}
    ordered = [by_id[h.chunk_id] for h in fused if h.chunk_id in by_id]
    for hit, ranked in zip(ordered, fused):
        hit.score = ranked.score
    hits = expand_neighbours(ordered[:k])
    return render_with_provenance(hits)


def expand_neighbours(hits: Sequence[ChunkHit], window: int = 1) -> list[ChunkHit]:
    """Include ordinal n-1..n+1 per artifact for each fused hit."""
    if not hits:
        return []
    wanted: dict[str, ChunkHit] = {}
    order: list[str] = []

    def _take(hit: ChunkHit) -> None:
        if hit.chunk_id in wanted:
            return
        wanted[hit.chunk_id] = hit
        order.append(hit.chunk_id)

    artifact_ids = {h.artifact_id for h in hits}
    neighbours_by_art = _chunks_for_artifacts(artifact_ids)
    for hit in hits:
        _take(hit)
        for other in neighbours_by_art.get(hit.artifact_id, []):
            if abs(other.ordinal - hit.ordinal) <= window and other.chunk_id != hit.chunk_id:
                other.neighbour = True
                other.score = hit.score
                _take(other)
    return [wanted[cid] for cid in order]


def render_with_provenance(hits: Sequence[ChunkHit]) -> str:
    """Never a chunk without artifact + locator (page, slide, or sheet)."""
    blocks: list[str] = []
    for hit in hits:
        locator = (hit.locator or "").strip()
        if not locator and hit.page is not None:
            locator = f"p.{hit.page}"
        if not hit.original_name or not locator:
            continue
        heading = hit.heading or "—"
        header = f"[{hit.original_name} / {locator} / {heading}]"
        blocks.append(f"{header}\n{hit.text.strip()}")
    return "\n\n".join(blocks)


def _label_matches(query: str, label: str) -> bool:
    q_norm = _normalize(query)
    l_norm = _normalize(label)
    if not q_norm or not l_norm:
        return False
    if l_norm in q_norm or q_norm in l_norm:
        return True
    for term in _tokens(query):
        if len(term) >= 3 and (term in l_norm or _trigram_sim(term, l_norm) >= TRIGRAM_THRESHOLD):
            return True
    return _trigram_sim(q_norm, l_norm) >= TRIGRAM_THRESHOLD


def _trigram_sim(a: str, b: str) -> float:
    ta, tb = _trigrams(a), _trigrams(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _trigrams(value: str) -> set[str]:
    padded = f"  {value.casefold()} "
    return {padded[i : i + 3] for i in range(len(padded) - 2)}


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _tokens(value: str) -> list[str]:
    return [t for t in _TOKEN.findall(value.casefold()) if t not in _STOP]


def _id_tail(node_id: str) -> str:
    return node_id.rsplit(":", 1)[-1]


def _props(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _page_from_location(location_json: str | None) -> int | None:
    if not location_json:
        return None
    try:
        data = json.loads(location_json)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    for key in ("page", "slide"):
        val = data.get(key)
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                continue
    return None


def _locator_from_location(location_json: str | None) -> str:
    if not location_json:
        return ""
    try:
        data = json.loads(location_json)
    except (TypeError, json.JSONDecodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    page = data.get("page")
    if page is not None:
        return f"p.{page}"
    slide = data.get("slide")
    if slide is not None:
        return f"slide {slide}"
    sheet = data.get("sheet")
    if sheet is not None and str(sheet).strip():
        return f"sheet {sheet}"
    return ""


def _heading_from_json(heading_path_json: str | None) -> str:
    if not heading_path_json:
        return ""
    try:
        data = json.loads(heading_path_json)
    except (TypeError, json.JSONDecodeError):
        return ""
    if isinstance(data, list):
        return " > ".join(str(p) for p in data if p)
    return str(data)


def _load_filtered_chunks(
    project_id: str,
    vendor: str | None,
    doc_role: str | None,
    chunk_type: str | None,
    artifact_ids: Sequence[str],
) -> list[ChunkHit]:
    clauses = ["c.project_id = :pid"]
    params: dict[str, Any] = {"pid": project_id}
    if vendor:
        clauses.append("a.vendor_id = :vendor")
        params["vendor"] = vendor
    if doc_role:
        clauses.append("a.doc_role = :doc_role")
        params["doc_role"] = doc_role
    if chunk_type:
        clauses.append("c.chunk_type = :chunk_type")
        params["chunk_type"] = chunk_type
    if artifact_ids:
        clauses.append("c.artifact_id IN :artifact_ids")
        params["artifact_ids"] = list(artifact_ids)
    sql = f"""
        SELECT c.id AS chunk_id, c.artifact_id, c.ordinal, c.text,
               c.heading_path_json, c.location_json, a.original_name
          FROM chunk c
          JOIN artifact a ON a.id = c.artifact_id
         WHERE {" AND ".join(clauses)}
         ORDER BY c.artifact_id, c.ordinal
    """
    stmt = text(sql)
    if artifact_ids:
        stmt = stmt.bindparams(bindparam("artifact_ids", expanding=True))
    with session_scope() as session:
        rows = session.execute(stmt, params).mappings().all()
    return [_row_to_hit(row) for row in rows]


def _chunks_for_artifacts(artifact_ids: Iterable[str]) -> dict[str, list[ChunkHit]]:
    ids = list(artifact_ids)
    if not ids:
        return {}
    stmt = text(
        """
        SELECT c.id AS chunk_id, c.artifact_id, c.ordinal, c.text,
               c.heading_path_json, c.location_json, a.original_name
          FROM chunk c
          JOIN artifact a ON a.id = c.artifact_id
         WHERE c.artifact_id IN :ids
         ORDER BY c.artifact_id, c.ordinal
        """
    ).bindparams(bindparam("ids", expanding=True))
    with session_scope() as session:
        rows = session.execute(stmt, {"ids": ids}).mappings().all()
    out: dict[str, list[ChunkHit]] = {}
    for row in rows:
        hit = _row_to_hit(row)
        out.setdefault(hit.artifact_id, []).append(hit)
    return out


def _row_to_hit(row: Any) -> ChunkHit:
    location = row["location_json"]
    page = _page_from_location(location)
    locator = _locator_from_location(location)
    if not locator and page is not None:
        locator = f"p.{page}"
    return ChunkHit(
        chunk_id=row["chunk_id"],
        artifact_id=row["artifact_id"],
        original_name=row["original_name"] or "",
        page=page,
        heading=_heading_from_json(row["heading_path_json"]),
        ordinal=int(row["ordinal"]),
        text=row["text"] or "",
        locator=locator,
    )


def _lexical_rank(query: str, chunks: Sequence[ChunkHit]) -> list[tuple[str, float]]:
    scored: list[tuple[str, float]] = []
    q_terms = _tokens(query)
    for chunk in chunks:
        score = _bm25_like(q_terms, chunk.text)
        if score > 0:
            scored.append((chunk.chunk_id, score))
    scored.sort(key=lambda item: (-item[1], item[0]))
    return scored


def _bm25_like(q_terms: Sequence[str], text: str) -> float:
    if not q_terms:
        return 0.0
    tokens = _TOKEN.findall(text.casefold())
    if not tokens:
        return 0.0
    from collections import Counter

    counts = Counter(tokens)
    n = len(tokens)
    score = 0.0
    for term in q_terms:
        tf = counts.get(term, 0)
        if not tf:
            continue
        score += (tf * (2.2 + 1.0)) / (tf + 2.2 * (0.25 + 0.75 * n / 50.0))
    return score


def _vector_rank(
    project_id: str,
    query: str,
    chunks: Sequence[ChunkHit],
    *,
    embed_fn: Any | None,
) -> list[tuple[str, float]]:
    if not chunks:
        return []
    stored = load_embeddings(project_id, [c.chunk_id for c in chunks])
    if not stored:
        return []
    try:
        qvec = embed_query(query, embed_fn=embed_fn)
    except RuntimeError:
        log.info("vector rank skipped (embeddings BLOCKED) project_id={}", project_id)
        return []
    scored: list[tuple[str, float]] = []
    for chunk in chunks:
        vec = stored.get(chunk.chunk_id)
        if not vec:
            continue
        sim = _cosine(qvec, vec)
        if sim > 0:
            scored.append((chunk.chunk_id, sim))
    scored.sort(key=lambda item: (-item[1], item[0]))
    return scored


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for i in range(n):
        dot += a[i] * b[i]
        na += a[i] * a[i]
        nb += b[i] * b[i]
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / math.sqrt(na * nb)
