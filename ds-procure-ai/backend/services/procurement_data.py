"""Procurement API payloads — constants and empty templates only."""

from __future__ import annotations

TABS = [
    {"id": "overview", "label": "Overview"},
    {"id": "workspace", "label": "Workspace"},
    {"id": "documents", "label": "Documents"},
    {"id": "requirements", "label": "Requirements"},
    {"id": "vendors", "label": "Vendors"},
    {"id": "activity", "label": "Activity"},
]

EMPTY_OVERVIEW_SECTIONS = {
    "stages": [],
    "metrics": [],
    "milestones": [],
    "insights": [],
    "requirements": {"total": 0, "approved": 0, "pending": 0, "rejected": 0},
    "vendors": {"invited": 0, "responded": 0, "shortlisted": 0},
    "approvals": [],
    "quickActions": [
        "Add Requirement",
        "Invite Vendor",
        "Compare Vendors",
        "AI Risk Assessment",
        "Generate Report",
    ],
}

EMPTY_WORKSPACE_GRAPH = {
    "edgeLabels": [],
    "edges": [],
    "nodes": [],
}

STORAGE_LIMIT_BYTES = 10 * 1024 * 1024 * 1024
