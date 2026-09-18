"""Chunk embeddings for hybrid retrieval (W6).

KB vectors live in `chunk_embedding`, not the LangGraph store.
Databricks `system.ai.gte-large-en` is 1024-d; batches of 64.

BLOCKED: live Lakebase/pgvector + Databricks `system.ai.gte-large-en`
until credentials are available. Tests and local sqlite inject `embed_fn`
(fake 1024-d vectors). Do not call Databricks from unit tests.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from typing import Any

from sqlalchemy import bindparam, text

from shared.db.connection import mate_table_name, session_scope
from shared.logger_global import get_logger

log = get_logger(__name__)

EMBEDDING_DIM = 1024
DEFAULT_BATCH_SIZE = 64
MODEL_ID = "system.ai.gte-large-en"
SQLITE_EMBEDDING_DDL = """
CREATE TABLE IF NOT EXISTS chunk_embedding (
  chunk_id VARCHAR PRIMARY KEY,
  project_id VARCHAR NOT NULL,
  vendor_id VARCHAR,
  doc_role VARCHAR,
  chunk_type VARCHAR,
  embedding TEXT NOT NULL,
  model_version VARCHAR NOT NULL
)
"""

EmbedFn = Callable[[Sequence[str]], list[list[float]]]


def ensure_embedding_table() -> None:
    """Sqlite stand-in for the Lakebase vector(1024) table (W0 postgres only)."""
    with session_scope() as session:
        bind = session.get_bind()
        if bind.dialect.name == "sqlite":
            session.execute(text(SQLITE_EMBEDDING_DDL))


def embed_texts(
    texts: Sequence[str],
    *,
    embed_fn: EmbedFn | None = None,
) -> list[list[float]]:
    """Embed a batch. Inject `embed_fn` in tests; live path is BLOCKED."""
    if not texts:
        return []
    fn = embed_fn or _live_embed
    vectors = fn(list(texts))
    if len(vectors) != len(texts):
        raise ValueError(f"embed_fn returned {len(vectors)} vectors for {len(texts)} texts")
    for vec in vectors:
        if len(vec) != EMBEDDING_DIM:
            raise ValueError(f"embedding dim {len(vec)} != {EMBEDDING_DIM}")
    return vectors


def embed_query(query: str, *, embed_fn: EmbedFn | None = None) -> list[float]:
    return embed_texts([query], embed_fn=embed_fn)[0]


def fake_embedding(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Deterministic unit-ish vector for tests (no model)."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vec = [0.0] * dim
    for i in range(0, min(len(digest), dim), 4):
        idx = int.from_bytes(digest[i : i + 4], "big") % dim
        vec[idx] = 1.0
    if not any(vec):
        vec[0] = 1.0
    return vec


def fake_embed_fn(texts: Sequence[str]) -> list[list[float]]:
    return [fake_embedding(t) for t in texts]


def _live_embed(texts: Sequence[str]) -> list[list[float]]:
    # BLOCKED: live Lakebase/pgvector + Databricks system.ai.gte-large-en.
    raise RuntimeError(
        "BLOCKED: live Databricks system.ai.gte-large-en / Lakebase pgvector"
    )


async def embed_pending_chunks(
    project_id: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
    *,
    embed_fn: EmbedFn | None = None,
    model_version: str = MODEL_ID,
) -> int:
    """Embed chunks that lack a row in chunk_embedding. Returns rows written."""
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    ensure_embedding_table()
    pending = _pending_chunks(project_id)
    written = 0
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        vectors = embed_texts([row["text"] for row in batch], embed_fn=embed_fn)
        _upsert_embeddings(batch, vectors, model_version)
        written += len(batch)
    log.info(
        "embed_pending_chunks project_id={} wrote={} batch_size={}",
        project_id,
        written,
        batch_size,
    )
    return written


def load_embeddings(project_id: str, chunk_ids: Sequence[str] | None = None) -> dict[str, list[float]]:
    ensure_embedding_table()
    sql = f"SELECT chunk_id, embedding FROM {mate_table_name('chunk_embedding')} WHERE project_id = :pid"
    params: dict[str, Any] = {"pid": project_id}
    stmt = text(sql)
    if chunk_ids:
        stmt = text(sql + " AND chunk_id IN :ids").bindparams(bindparam("ids", expanding=True))
        params["ids"] = list(chunk_ids)
    with session_scope() as session:
        rows = session.execute(stmt, params).mappings().all()
    out: dict[str, list[float]] = {}
    for row in rows:
        raw = row["embedding"]
        if isinstance(raw, str):
            out[row["chunk_id"]] = [float(x) for x in json.loads(raw)]
        else:
            out[row["chunk_id"]] = list(raw)
    return out


def _pending_chunks(project_id: str) -> list[dict[str, Any]]:
    ensure_embedding_table()
    chunk = mate_table_name("chunk")
    artifact = mate_table_name("artifact")
    chunk_embedding = mate_table_name("chunk_embedding")
    sql = f"""
        SELECT c.id AS chunk_id, c.project_id, c.chunk_type, c.text,
               a.vendor_id, a.doc_role
          FROM {chunk} c
          JOIN {artifact} a ON a.id = c.artifact_id
         WHERE c.project_id = :pid
           AND c.id NOT IN (SELECT chunk_id FROM {chunk_embedding} WHERE project_id = :pid)
         ORDER BY c.artifact_id, c.ordinal
    """
    with session_scope() as session:
        return [dict(row) for row in session.execute(text(sql), {"pid": project_id}).mappings().all()]


def _upsert_embeddings(
    rows: Sequence[dict[str, Any]],
    vectors: Sequence[Sequence[float]],
    model_version: str,
) -> None:
    with session_scope() as session:
        chunk_embedding = mate_table_name("chunk_embedding")
        for row, vec in zip(rows, vectors, strict=True):
            session.execute(
                text(
                    f"""
                    INSERT INTO {chunk_embedding}
                      (chunk_id, project_id, vendor_id, doc_role, chunk_type, embedding, model_version)
                    VALUES
                      (:chunk_id, :project_id, :vendor_id, :doc_role, :chunk_type, :embedding, :model_version)
                    ON CONFLICT (chunk_id) DO UPDATE SET
                      embedding = excluded.embedding,
                      model_version = excluded.model_version,
                      vendor_id = excluded.vendor_id,
                      doc_role = excluded.doc_role,
                      chunk_type = excluded.chunk_type
                    """
                ),
                {
                    "chunk_id": row["chunk_id"],
                    "project_id": row["project_id"],
                    "vendor_id": row.get("vendor_id"),
                    "doc_role": row.get("doc_role"),
                    "chunk_type": row.get("chunk_type"),
                    "embedding": json.dumps(list(vec)),
                    "model_version": model_version,
                },
            )
