"""W2 async ingest: parse/extract overlap, failure isolation, RFP priority."""

from __future__ import annotations

import asyncio
import time

import pytest

from ai_brain.core.kb.ingest import ingest_project, is_rfp_priority
from shared.db.models import Artifact, utc_now_iso


def _artifact(artifact_id: str, name: str = "vendor.pdf", doc_role: str | None = None) -> Artifact:
    now = utc_now_iso()
    return Artifact(
        id=artifact_id,
        project_id="p1",
        uploaded_by="u1",
        kind="upload",
        original_name=name,
        storage_relpath=f"rel/{artifact_id}",
        created_at=now,
        parse_status="pending",
        doc_role=doc_role,
    )


def test_rfp_priority_from_filename_and_role():
    assert is_rfp_priority(_artifact("a", "Etex_RFP_pack.pdf"))
    assert is_rfp_priority(_artifact("b", "notes.pdf", doc_role="rfp"))
    assert not is_rfp_priority(_artifact("c", "Vendor_proposal.pdf"))


@pytest.mark.asyncio
async def test_ingest_extract_overlaps_parse():
    catalog = {
        "fast": _artifact("fast", "Vendor_A.pdf"),
        "slow": _artifact("slow", "Vendor_B.pdf"),
    }
    events: list[tuple[str, str, float]] = []

    def on_event(event: str, **fields) -> None:
        events.append((event, str(fields.get("artifact_id") or ""), time.perf_counter()))

    async def parse_fn(artifact: Artifact) -> Artifact:
        if artifact.id == "slow":
            await asyncio.sleep(0.35)
        artifact.parse_status = "ok"
        return artifact

    async def extract_fn(artifact: Artifact, _doc) -> None:
        await asyncio.sleep(0.02)

    report = await ingest_project(
        "p1",
        ["fast", "slow"],
        on_event=on_event,
        parse_fn=parse_fn,
        extract_fn=extract_fn,
        quality_fn=lambda _artifact: None,
        embed_fn=lambda _pid: None,
        graph_fn=lambda _pid: None,
        load_artifact_fn=catalog.__getitem__,
        parse_concurrency=4,
        extract_concurrency=8,
    )

    extract_starts = [stamp for event, _aid, stamp in events if event == "extract_start"]
    parse_dones = [stamp for event, _aid, stamp in events if event == "parse_done"]
    assert extract_starts, events
    assert parse_dones, events
    fast_extract = next(stamp for event, aid, stamp in events if event == "extract_start" and aid == "fast")
    slow_parse_done = next(stamp for event, aid, stamp in events if event == "parse_done" and aid == "slow")
    assert fast_extract < slow_parse_done, events
    assert min(extract_starts) < max(parse_dones)
    assert "fast" in report.parsed_ok
    assert "fast" in report.extracted_ok
    assert not report.failures


@pytest.mark.asyncio
async def test_ingest_one_parse_failure_does_not_kill_batch():
    catalog = {
        "ok": _artifact("ok", "Vendor_A.pdf"),
        "boom": _artifact("boom", "broken.pdf"),
    }

    async def parse_fn(artifact: Artifact) -> Artifact:
        if artifact.id == "boom":
            raise RuntimeError("parse exploded")
        artifact.parse_status = "ok"
        return artifact

    extracted: list[str] = []

    async def extract_fn(artifact: Artifact, _doc) -> None:
        extracted.append(artifact.id)

    order: list[str] = []

    async def embed_fn(project_id: str) -> None:
        order.append("embed")

    async def graph_fn(project_id: str) -> None:
        order.append("graph")

    report = await ingest_project(
        "p1",
        ["ok", "boom"],
        parse_fn=parse_fn,
        extract_fn=extract_fn,
        quality_fn=lambda _artifact: None,
        embed_fn=embed_fn,
        graph_fn=graph_fn,
        load_artifact_fn=catalog.__getitem__,
    )

    assert extracted == ["ok"]
    assert "ok" in report.parsed_ok
    assert any(aid == "boom" for aid, _msg in report.failures)
    assert order == ["embed", "graph"]


@pytest.mark.asyncio
async def test_ingest_rfp_has_extract_queue_priority():
    catalog = {
        "vendor_fast": _artifact("vendor_fast", "Vendor_A.pdf"),
        "rfp": _artifact("rfp", "Etex_RFP_Swift.pdf"),
        "vendor_late": _artifact("vendor_late", "Vendor_B.pdf"),
    }
    extract_order: list[str] = []

    async def parse_fn(artifact: Artifact) -> Artifact:
        if artifact.id != "vendor_fast":
            await asyncio.sleep(0.05)
        artifact.parse_status = "ok"
        return artifact

    async def extract_fn(artifact: Artifact, _doc) -> None:
        extract_order.append(artifact.id)
        if artifact.id == "vendor_fast":
            await asyncio.sleep(0.12)

    await ingest_project(
        "p1",
        ["vendor_fast", "rfp", "vendor_late"],
        parse_fn=parse_fn,
        extract_fn=extract_fn,
        quality_fn=lambda _artifact: None,
        embed_fn=lambda _pid: None,
        graph_fn=lambda _pid: None,
        load_artifact_fn=catalog.__getitem__,
        extract_concurrency=1,
    )

    assert extract_order[0] == "vendor_fast"
    assert extract_order[1] == "rfp"
    assert extract_order[2] == "vendor_late"
