"""W6 search RRF + embed mock (no live Databricks / pgvector)."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from ai_brain.core.kb.embed import (
    EMBEDDING_DIM,
    DEFAULT_BATCH_SIZE,
    embed_pending_chunks,
    embed_texts,
    fake_embed_fn,
    load_embeddings,
)
from ai_brain.core.kb.search import graph_expand_entities, rrf, search_kb
from shared.db.models import utc_now_iso


@pytest.fixture()
def db_env(monkeypatch):
    from shared.db import init_db
    from shared.db import connection as db_connection

    if db_connection._engine is not None:
        db_connection._engine.dispose()
    db_connection._engine = None
    db_connection._SessionLocal = None
    tmp = tempfile.mkdtemp()
    db_path = Path(tmp) / "test.sqlite"
    monkeypatch.setenv("MATE_SQLITE_PATH", str(db_path))
    init_db()
    yield db_path
    if db_connection._engine is not None:
        db_connection._engine.dispose()
    db_connection._engine = None
    db_connection._SessionLocal = None
    shutil.rmtree(tmp, ignore_errors=True)


def test_rrf_fusion_is_deterministic_on_fixed_candidate_set():
    bm25 = [("c1", 0.9), ("c2", 0.5), ("c3", 0.1)]
    vec = [("c3", 0.99), ("c1", 0.4), ("c4", 0.2)]
    fused = rrf([bm25, vec], k0=60)
    ids = [hit.chunk_id for hit in fused]
    assert ids == ["c1", "c3", "c2", "c4"]
    assert fused[0].score == pytest.approx(1 / 61 + 1 / 62)
    assert fused[1].score == pytest.approx(1 / 63 + 1 / 61)
    assert rrf([bm25, vec], k0=60) == fused
    assert rrf([list(bm25), list(vec)], k0=60) == fused


def test_fake_embeddings_are_1024d():
    vectors = embed_texts(["Inetum pricing", "TriFinance rates"], embed_fn=fake_embed_fn)
    assert len(vectors) == 2
    assert all(len(v) == EMBEDDING_DIM for v in vectors)
    assert DEFAULT_BATCH_SIZE == 64


def test_live_embed_is_blocked():
    with pytest.raises(RuntimeError, match="BLOCKED"):
        embed_texts(["hello"])


def _seed_project():
    from shared.db.connection import session_scope
    from shared.db.models import AppUser, Project

    now = utc_now_iso()
    with session_scope() as session:
        session.add(AppUser(workspace_id="u1", created_at=now, updated_at=now))
        session.add(
            Project(
                id="p1",
                code="PRJ-TEST",
                owner_id="u1",
                module_id="procurement-ai-assistant",
                name="t",
                status="Active",
                priority="Medium",
                progress=0,
                created_at=now,
                updated_at=now,
            )
        )


def _add_artifact(session, artifact_id: str, name: str, vendor_id: str, doc_role: str) -> None:
    from shared.db.models import Artifact

    now = utc_now_iso()
    session.add(
        Artifact(
            id=artifact_id,
            project_id="p1",
            uploaded_by="u1",
            kind="upload",
            original_name=name,
            storage_relpath=f"rel/{artifact_id}",
            created_at=now,
            parse_status="ok",
            vendor_id=vendor_id,
            doc_role=doc_role,
        )
    )


def _add_chunk(session, chunk_id: str, artifact_id: str, ordinal: int, text: str, page: int, heading: str) -> None:
    from shared.db.models import Chunk

    now = utc_now_iso()
    session.add(
        Chunk(
            id=chunk_id,
            project_id="p1",
            artifact_id=artifact_id,
            ordinal=ordinal,
            chunk_type="text",
            text=text,
            token_count=len(text.split()),
            heading_path_json=json.dumps([heading]),
            location_json=json.dumps({"page": page}),
            created_at=now,
        )
    )


def _seed_consortium_graph():
    from shared.db.connection import session_scope
    from shared.db.models import KbEdge, KbNode

    _seed_project()
    now = utc_now_iso()
    with session_scope() as session:
        _add_artifact(
            session,
            "art-inetum",
            "TF Inetum Proposal Etex CSP Assessment.pdf",
            "inetum",
            "proposal",
        )
        _add_artifact(
            session,
            "art-trifinance",
            "TRIFINANCE_BELGIUM_NV_BE-X-882734939.pdf",
            "trifinance",
            "registry",
        )
        _add_chunk(
            session,
            "c-inetum",
            "art-inetum",
            0,
            "Inetum delivers the CSP questionnaires for Etex.",
            3,
            "Approach",
        )
        _add_chunk(
            session,
            "c-tf-0",
            "art-trifinance",
            0,
            "Company extract for TriFinance Belgium NV.",
            1,
            "Cover",
        )
        _add_chunk(
            session,
            "c-tf-pricing",
            "art-trifinance",
            1,
            "Day rate 850 EUR pricing for senior consultant.",
            5,
            "Pricing",
        )
        _add_chunk(
            session,
            "c-tf-2",
            "art-trifinance",
            2,
            "Payment terms net 30 days after invoice.",
            6,
            "Terms",
        )
        _add_artifact(
            session,
            "art-ey",
            "EY_pricing_annex.pdf",
            "ey",
            "pricing",
        )
        _add_chunk(
            session,
            "c-ey-pricing",
            "art-ey",
            0,
            "EY day rate pricing 1200 EUR.",
            2,
            "Pricing",
        )
        session.add(
            KbNode(
                id="p1:LegalEntity:inetum",
                project_id="p1",
                type="LegalEntity",
                label="Inetum",
                source_artifact_id="art-inetum",
                source_page=1,
                confidence=1.0,
                model_version="fixture",
            )
        )
        session.add(
            KbNode(
                id="p1:LegalEntity:trifinance",
                project_id="p1",
                type="LegalEntity",
                label="TriFinance",
                source_artifact_id="art-trifinance",
                source_page=1,
                confidence=1.0,
                model_version="fixture",
            )
        )
        session.add(
            KbNode(
                id="p1:Bid:trifinance-inetum",
                project_id="p1",
                type="Bid",
                label="TriFinance & Inetum",
                props=json.dumps({"bid_id": "trifinance-inetum"}),
                source_artifact_id="art-inetum",
                source_page=1,
                confidence=1.0,
                model_version="fixture",
            )
        )
        session.flush()
        session.add(
            KbEdge(
                id="e-inetum-member",
                project_id="p1",
                src="p1:LegalEntity:inetum",
                dst="p1:Bid:trifinance-inetum",
                type="MEMBER_OF_CONSORTIUM",
                source_artifact_id="art-inetum",
                source_page=1,
                confidence=1.0,
                model_version="fixture",
            )
        )
        session.add(
            KbEdge(
                id="e-tf-member",
                project_id="p1",
                src="p1:LegalEntity:trifinance",
                dst="p1:Bid:trifinance-inetum",
                type="MEMBER_OF_CONSORTIUM",
                source_artifact_id="art-trifinance",
                source_page=1,
                confidence=1.0,
                model_version="fixture",
            )
        )
    return now


def test_consortium_expansion_returns_trifinance_artifacts_for_inetum_query(db_env):
    _seed_consortium_graph()
    artifact_ids = graph_expand_entities("p1", "Inetum")
    assert "art-trifinance" in artifact_ids
    assert "art-inetum" in artifact_ids

    rendered = search_kb("Inetum pricing", k=8, project_id="p1")
    assert "TRIFINANCE_BELGIUM_NV_BE-X-882734939.pdf" in rendered
    assert "p.5" in rendered
    assert "Pricing" in rendered
    assert "EY_pricing_annex.pdf" not in rendered


@pytest.mark.asyncio
async def test_embed_pending_chunks_batches_64_with_fake_vectors(db_env):
    _seed_project()
    from shared.db.connection import session_scope

    with session_scope() as session:
        _add_artifact(session, "art-batch", "batch.pdf", "ey", "proposal")
        for i in range(70):
            _add_chunk(session, f"c-batch-{i}", "art-batch", i, f"chunk body {i} pricing", 1, "Body")

    calls: list[int] = []

    def counting_embed(texts):
        calls.append(len(texts))
        return fake_embed_fn(texts)

    written = await embed_pending_chunks("p1", batch_size=64, embed_fn=counting_embed)
    assert written == 70
    assert calls == [64, 6]
    stored = load_embeddings("p1")
    assert len(stored) == 70
    assert all(len(v) == EMBEDDING_DIM for v in stored.values())
    again = await embed_pending_chunks("p1", batch_size=64, embed_fn=counting_embed)
    assert again == 0
