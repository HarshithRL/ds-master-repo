"""HITL gates as interrupt round-trips (W9).

Order of cheapness: vendor roster (W3) → requirement list (after
`extract_requirements`) → pre-publish matrix review (W8).

Studio UI round-trip is BLOCKED (needs Studio HITL test). This module is
the server contract: interrupt payload + approve/edit/reject resume.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

GateName = Literal["vendor_roster", "requirement_list", "pre_publish"]
ResumeAction = Literal["approve", "edit", "reject"]

GATE_ORDER: tuple[GateName, ...] = (
    "vendor_roster",
    "requirement_list",
    "pre_publish",
)
ACTIONS: tuple[ResumeAction, ...] = ("approve", "edit", "reject")
GATES = frozenset(GATE_ORDER)


class HitlRequest(BaseModel):
    """Payload carried on `event: interrupt` — the HITL request."""

    gate: GateName
    thread_id: str | None = None
    title: str = ""
    summary: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    actions: tuple[ResumeAction, ...] = ACTIONS


class HitlDecision(BaseModel):
    """Resume body for a gate. Pass-through to brain `Command(resume=...)`."""

    gate: GateName
    action: ResumeAction
    edits: dict[str, Any] | None = None
    checkpoint_id: str | None = None


class HitlResumeResult(BaseModel):
    ok: bool
    status: Literal["approved", "edited", "rejected"]
    gate: GateName
    next_gate: GateName | None = None
    edits: dict[str, Any] | None = None
    detail: str = ""


_TITLES: dict[GateName, str] = {
    "vendor_roster": "Confirm vendor roster",
    "requirement_list": "Confirm requirement list",
    "pre_publish": "Pre-publish matrix review",
}


def next_gate(gate: str) -> GateName | None:
    if gate not in GATES:
        raise ValueError(f"unknown HITL gate {gate!r}")
    idx = GATE_ORDER.index(gate)  # type: ignore[arg-type]
    if idx + 1 >= len(GATE_ORDER):
        return None
    return GATE_ORDER[idx + 1]


def build_hitl_request(
    gate: GateName,
    *,
    thread_id: str | None = None,
    payload: dict[str, Any] | None = None,
    summary: str = "",
) -> HitlRequest:
    return HitlRequest(
        gate=gate,
        thread_id=thread_id,
        title=_TITLES[gate],
        summary=summary,
        payload=payload or {},
        actions=ACTIONS,
    )


def hitl_request_from_interrupts(interrupts: Any) -> dict[str, Any]:
    """Best-effort HITL request from brain `custom_outputs.interrupts`."""
    items = interrupts if isinstance(interrupts, list) else [interrupts]
    for item in items:
        value = item
        if isinstance(item, dict) and "value" in item and "gate" not in item:
            value = item.get("value")
        if isinstance(value, dict) and value.get("gate") in GATES:
            return HitlRequest.model_validate(
                {
                    "gate": value["gate"],
                    "thread_id": value.get("thread_id"),
                    "title": value.get("title") or _TITLES[value["gate"]],
                    "summary": value.get("summary") or "",
                    "payload": value.get("payload") or {},
                }
            ).model_dump()
    return {"interrupts": interrupts, "actions": list(ACTIONS), "gates": list(GATE_ORDER)}


def apply_resume(decision: HitlDecision | dict[str, Any]) -> HitlResumeResult:
    """Validate approve/edit/reject. Does not call Studio or mutate the graph."""
    if isinstance(decision, dict):
        try:
            decision = HitlDecision.model_validate(decision)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
    if decision.action == "reject":
        return HitlResumeResult(
            ok=False,
            status="rejected",
            gate=decision.gate,
            next_gate=None,
            detail=f"{decision.gate} rejected",
        )
    if decision.action == "edit":
        if not decision.edits:
            raise ValueError("edit requires edits")
        return HitlResumeResult(
            ok=True,
            status="edited",
            gate=decision.gate,
            next_gate=next_gate(decision.gate),
            edits=decision.edits,
            detail=f"{decision.gate} edited",
        )
    return HitlResumeResult(
        ok=True,
        status="approved",
        gate=decision.gate,
        next_gate=next_gate(decision.gate),
        detail=f"{decision.gate} approved",
    )


def resume_command_payload(decision: HitlDecision | dict[str, Any]) -> dict[str, Any]:
    """Shape forwarded to brain `POST /v1/threads/{id}/resume`."""
    result = apply_resume(decision)
    body = decision if isinstance(decision, HitlDecision) else HitlDecision.model_validate(decision)
    return {
        "gate": body.gate,
        "action": body.action,
        "edits": body.edits,
        "result": result.model_dump(),
    }
