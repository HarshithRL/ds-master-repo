"""W7 graph entity resolution, closed vocab, independence CTE."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import select

from ai_brain.core.kb.store.graph import (
    ClosedVocabularyViolation,
    GraphEdge,
    GraphProposal,
    detect_independence_conflicts,
    resolve_entities_and_write_graph,
    validate_and_filter_edges,
)
from ai_brain.core.kb.api.schemas import EntityMention
from shared.db.models import KbEdge, QualityFlag, utc_now_iso


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


def test_unknown_edge_type_raises_never_coerce():
    with pytest.raises(ClosedVocabularyViolation, match="RELATED_TO"):
        validate_and_filter_edges(
            [
                GraphEdge(
                    type="RELATED_TO",
                    src_key="a",
                    dst_key="b",
                    source_artifact_id="art-1",
                    source_page=1,
                )
            ]
        )


def test_uncited_edges_are_dropped():
    cited, dropped = validate_and_filter_edges(
        [
            GraphEdge(
                type="PARENT_OF",
                src_key="kpmg-group",
                dst_key="kpmg-advisory",
                source_artifact_id="art-kpmg",
                source_page=2,
            ),
            GraphEdge(
                type="MEMBER_OF_CONSORTIUM",
                src_key="inetum",
                dst_key="consortium",
                dst_type="Bid",
            ),
        ]
    )
    assert dropped == 1
    assert len(cited) == 1
    assert cited[0].type == "PARENT_OF"


@pytest.mark.asyncio
async def test_consortium_and_kpmg_parent_edges_have_citations(db_env):
    _seed_project()
    mentions = [
        EntityMention(name="Inetum", artifact_id="art-consortium", page=1),
        EntityMention(
            name="TriFinance",
            registry_id="BE-X-882734939",
            artifact_id="art-consortium",
            page=1,
        ),
        EntityMention(
            name="KPMG Advisory SRL",
            registry_id="BE-X-439819279",
            artifact_id="art-kpmg-adv",
            page=2,
        ),
        EntityMention(
            name="KPMG Belgium BV (Group)",
            artifact_id="art-kpmg-group",
            page=1,
        ),
    ]
    report = await resolve_entities_and_write_graph("p1", mentions=mentions)
    assert report.edges_dropped_uncited == 0
    assert isinstance(report.independence_chains, list)

    from shared.db.connection import session_scope

    with session_scope() as session:
        edges = session.scalars(select(KbEdge).where(KbEdge.project_id == "p1")).all()
        types = {row.type for row in edges}
        assert "MEMBER_OF_CONSORTIUM" in types
        assert "PARENT_OF" in types
        for row in edges:
            assert row.source_artifact_id
            assert row.source_page is not None
        members = [e for e in edges if e.type == "MEMBER_OF_CONSORTIUM"]
        assert len(members) == 2
        parents = [e for e in edges if e.type == "PARENT_OF"]
        assert len(parents) == 1
        assert parents[0].source_artifact_id in {"art-kpmg-adv", "art-kpmg-group"}


@pytest.mark.asyncio
async def test_unknown_edge_type_aborts_write(db_env):
    _seed_project()

    def bad_resolver(seed: GraphProposal) -> GraphProposal:
        return GraphProposal(
            nodes=list(seed.nodes),
            edges=[
                GraphEdge(
                    type="WORKS_WITH",
                    src_key="inetum",
                    dst_key="trifinance",
                    source_artifact_id="art-x",
                    source_page=1,
                )
            ],
        )

    with pytest.raises(ClosedVocabularyViolation):
        await resolve_entities_and_write_graph(
            "p1",
            mentions=[EntityMention(name="Inetum", artifact_id="art-x", page=1)],
            resolver=bad_resolver,
        )


@pytest.mark.asyncio
async def test_independence_cte_flags_bidder_as_subcontractor(db_env):
    _seed_project()
    from shared.db.connection import session_scope
    from shared.db.models import KbNode

    with session_scope() as session:
        for node_id, ntype, label in (
            ("p1:LegalEntity:inetum", "LegalEntity", "Inetum"),
            ("p1:LegalEntity:pwc", "LegalEntity", "PwC"),
            ("p1:Bid:consortium", "Bid", "TriFinance & Inetum"),
            ("p1:Bid:pwc", "Bid", "PwC"),
            ("p1:Artifact:rfp", "Artifact", "RFP"),
        ):
            session.add(
                KbNode(
                    id=node_id,
                    project_id="p1",
                    type=ntype,
                    label=label,
                    source_artifact_id="art-sub",
                    source_page=4,
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
                dst="p1:Bid:consortium",
                type="MEMBER_OF_CONSORTIUM",
                source_artifact_id="art-consortium",
                source_page=1,
                confidence=1.0,
                model_version="fixture",
            )
        )
        session.add(
            KbEdge(
                id="e-pwc-member",
                project_id="p1",
                src="p1:LegalEntity:pwc",
                dst="p1:Bid:pwc",
                type="MEMBER_OF_CONSORTIUM",
                source_artifact_id="art-pwc",
                source_page=1,
                confidence=1.0,
                model_version="fixture",
            )
        )
        session.add(
            KbEdge(
                id="e-bid-a",
                project_id="p1",
                src="p1:Bid:consortium",
                dst="p1:Artifact:rfp",
                type="BIDS_ON",
                source_artifact_id="art-consortium",
                source_page=1,
                confidence=1.0,
                model_version="fixture",
            )
        )
        session.add(
            KbEdge(
                id="e-bid-b",
                project_id="p1",
                src="p1:Bid:pwc",
                dst="p1:Artifact:rfp",
                type="BIDS_ON",
                source_artifact_id="art-pwc",
                source_page=1,
                confidence=1.0,
                model_version="fixture",
            )
        )
        session.add(
            KbEdge(
                id="e-sub",
                project_id="p1",
                src="p1:LegalEntity:inetum",
                dst="p1:LegalEntity:pwc",
                type="SUBCONTRACTS_TO",
                source_artifact_id="art-sub",
                source_page=4,
                confidence=1.0,
                model_version="fixture",
            )
        )

    chains, flagged = detect_independence_conflicts("p1")
    assert chains, "independence CTE must run and return reachability rows"
    assert flagged == 1

    with session_scope() as session:
        flags = session.scalars(
            select(QualityFlag).where(QualityFlag.kind == "independence_conflict")
        ).all()
        assert flags
        assert flags[0].severity == "high"
        conflict_edges = session.scalars(
            select(KbEdge).where(KbEdge.type == "CONFLICTS_WITH")
        ).all()
        assert conflict_edges
        assert conflict_edges[0].source_artifact_id == "art-sub"
        assert conflict_edges[0].source_page == 4
