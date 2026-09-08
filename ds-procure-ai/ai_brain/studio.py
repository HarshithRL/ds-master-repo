"""LangGraph Studio exports for the existing Nexus and Procura workflows.

This module deliberately does not import ``brain_server`` or start
``GraphRuntime``. The LangGraph development server owns local persistence,
while the application keeps using its MLflow AgentServer on :8004.
"""

from __future__ import annotations

from ai_brain.server.tracing import configure_tracing

# Configure autologging before importing graph nodes. This runs only in the
# Studio process and leaves the application runtime configuration unchanged.
configure_tracing()

from ai_brain.core.procurement_ai.procura_graph import build_procura_ai
from ai_brain.nexus_graph import build_nexes_graph

# Do not supply the application's checkpointer/store; langgraph dev provides
# isolated local persistence for these compiled graphs.
nexus = build_nexes_graph()
procura = build_procura_ai()
