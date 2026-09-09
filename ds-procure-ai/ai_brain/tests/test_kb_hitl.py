"""W9 HITL gates: roster → requirements → pre-publish (interrupt round-trip, no Studio)."""

from __future__ import annotations

import pytest

from ai_brain.core.kb.build.hitl import (
    GATE_ORDER,
    HitlDecision,
    apply_resume,
    build_hitl_request,
    hitl_request_from_interrupts,
    next_gate,
    resume_command_payload,
)


def test_gate_order_roster_then_requirements_then_pre_publish():
    assert GATE_ORDER == ("vendor_roster", "requirement_list", "pre_publish")
    assert next_gate("vendor_roster") == "requirement_list"
    assert next_gate("requirement_list") == "pre_publish"
    assert next_gate("pre_publish") is None


def test_build_and_parse_interrupt_request():
    req = build_hitl_request(
        "vendor_roster",
        thread_id="p1",
        payload={"bids": ["bdo", "trifinance-inetum"]},
    )
    parsed = hitl_request_from_interrupts([req.model_dump()])
    assert parsed["gate"] == "vendor_roster"
    assert parsed["payload"]["bids"] == ["bdo", "trifinance-inetum"]


def test_apply_resume_approve_edit_reject():
    approved = apply_resume({"gate": "vendor_roster", "action": "approve"})
    assert approved.ok is True
    assert approved.next_gate == "requirement_list"

    edited = apply_resume(
        HitlDecision(
            gate="requirement_list",
            action="edit",
            edits={"requirements": [{"id": "r1", "text": "A4 both BICs"}]},
        )
    )
    assert edited.status == "edited"
    assert edited.next_gate == "pre_publish"

    rejected = apply_resume({"gate": "pre_publish", "action": "reject"})
    assert rejected.ok is False
    assert rejected.next_gate is None


def test_edit_without_edits_fails():
    with pytest.raises(ValueError, match="edits"):
        apply_resume({"gate": "vendor_roster", "action": "edit"})


def test_resume_command_payload_is_pass_through_shape():
    body = resume_command_payload({"gate": "pre_publish", "action": "approve"})
    assert body["gate"] == "pre_publish"
    assert body["action"] == "approve"
    assert body["result"]["ok"] is True
