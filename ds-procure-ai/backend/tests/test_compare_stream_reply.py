"""Extra map_brain_event cases for compare_xlsx assistant_reply + href."""

from __future__ import annotations

from services.procurement_chat import StreamAcc, map_brain_event


def test_final_done_prefers_assistant_reply_over_streamed_essay():
    acc = StreamAcc()
    list(
        map_brain_event(
            {
                "type": "response.output_text.delta",
                "delta": "I'll systematically read every chunk...",
                "custom_outputs": {"kind": "answer", "node": "model"},
            },
            acc,
        )
    )
    done = list(
        map_brain_event(
            {
                "type": "response.output_item.done",
                "item": {
                    "content": [
                        {
                            "type": "output_text",
                            "text": "I'll systematically read every chunk...",
                        }
                    ]
                },
                "custom_outputs": {
                    "kind": "answer",
                    "final": True,
                    "xlsx_href": "/api/procurement/projects/p1/packs/xlsx/download",
                    "values": {
                        "procurement": {
                            "assistant_reply": (
                                "Comparison workbook is ready. "
                                "Rows that do not apply to this process type are N/A. "
                                "Unevidenced cells are ?. Scorecard is left for the Etex team. "
                                "Download: /api/procurement/projects/p1/packs/xlsx/download"
                            ),
                            "xlsx_href": "/api/procurement/projects/p1/packs/xlsx/download",
                        }
                    },
                },
            },
            acc,
        )
    )
    assert len(done) == 1
    assert done[0]["type"] == "done"
    assert "I'll systematically" not in done[0]["text"]
    assert "Comparison workbook is ready." in done[0]["text"]
    assert done[0]["xlsx_href"].endswith("/packs/xlsx/download")
    assert "Download:" in done[0]["text"]


def test_final_done_appends_href_when_missing_from_text():
    acc = StreamAcc()
    done = list(
        map_brain_event(
            {
                "type": "response.output_item.done",
                "item": {"content": [{"text": "Workbook ready."}]},
                "custom_outputs": {
                    "kind": "answer",
                    "final": True,
                    "xlsx_href": "/api/procurement/projects/p9/packs/xlsx/download",
                    "values": {
                        "procurement": {
                            "assistant_reply": "Workbook ready.",
                            "xlsx_href": "/api/procurement/projects/p9/packs/xlsx/download",
                        }
                    },
                },
            },
            acc,
        )
    )
    assert done[0]["text"].endswith(
        "Download: /api/procurement/projects/p9/packs/xlsx/download"
    )


def test_nested_thought_delta_stays_out_of_answer():
    acc = StreamAcc()
    events = list(
        map_brain_event(
            {
                "type": "response.output_text.delta",
                "delta": "Delegating to vendor_analyst...",
                "custom_outputs": {"kind": "thought", "node": "comparison_orchestrator"},
            },
            acc,
        )
    )
    assert events[0]["type"] == "thought"
    assert acc.answer == ""
    assert "Delegating" in acc.thoughts[0]["detail"]
