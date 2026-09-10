from __future__ import annotations

import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Optional

import mlflow
from langchain.agents.middleware import ModelRequest, dynamic_prompt
from langchain_core.runnables import RunnableConfig
from mlflow.entities import SpanType

from ai_brain.core.kb.store.search import set_current_project_id
from ai_brain.core.procurement_ai.capabilities import project_id_from_state
from ai_brain.core.procurement_ai.knowledge import knowledge_prompt_block
from ai_brain.core.utils import read_prompt
from ai_brain.core.utils.content import content_text
from shared.logger_global import get_logger

log = get_logger(__name__, service="ai_brain")

LTM_LIMIT = 3
_MEMORY_NS_TAIL = "memories"


@dataclass
class ProcuraContext:
    project_id: str = ""
    user_id: str = ""
    memory_block: str = ""


def _context_field(context: Any, name: str) -> str:
    if context is None:
        return ""
    if isinstance(context, dict):
        return str(context.get(name) or "").strip()
    return str(getattr(context, name, "") or "").strip()


def _context_project_id(context: Any) -> str:
    return _context_field(context, "project_id")


def project_id_for_agent(state: dict[str, Any], config: RunnableConfig | None) -> str:
    project_id = project_id_from_state(state)
    if project_id:
        return project_id
    if isinstance(config, dict):
        cfg = config.get("configurable") or {}
        return str(cfg.get("project_id") or cfg.get("thread_id") or "").strip()
    return ""


def _user_id_from_config(config: RunnableConfig | None) -> str:
    if isinstance(config, dict):
        return str((config.get("configurable") or {}).get("user_id") or "").strip() or "anonymous"
    return "anonymous"


def _runtime_project_id(request: ModelRequest) -> str:
    runtime = getattr(request, "runtime", None)
    project_id = _context_project_id(getattr(runtime, "context", None) if runtime else None)
    if project_id:
        return project_id
    config = getattr(runtime, "config", None) if runtime else None
    if isinstance(config, dict):
        cfg = config.get("configurable") or {}
        return str(cfg.get("project_id") or cfg.get("thread_id") or "").strip()
    return ""


def _last_user_text(messages: Any) -> str:
    for message in reversed(list(messages or [])):
        if isinstance(message, dict):
            role = str(message.get("role") or message.get("type") or "")
            content = message.get("content")
        else:
            role = str(getattr(message, "type", "") or getattr(message, "role", "") or "")
            content = getattr(message, "content", "")
        if role in {"user", "human"}:
            return content_text(content)
    return ""


def conversation_messages(state: dict[str, Any]) -> list[Any]:
    """STM: checkpointed thread messages, else the current request string."""
    existing = list(state.get("messages") or [])
    if existing:
        return existing
    return [{"role": "user", "content": state.get("request") or "Hello"}]


def memory_namespace(user_id: str, project_id: str) -> tuple[str, str, str]:
    uid = (user_id or "anonymous").strip() or "anonymous"
    pid = (project_id or "_").strip() or "_"
    return (uid, pid, _MEMORY_NS_TAIL)


def remember_payload(text: str) -> str | None:
    """Return the utterance to persist when the user explicitly asks to remember."""
    stripped = (text or "").strip()
    if "remember" not in stripped.lower():
        return None
    return stripped


def format_memory_block(items: list[Any]) -> str:
    lines: list[str] = []
    for item in items:
        value = getattr(item, "value", None) or {}
        if not isinstance(value, dict):
            continue
        text = str(value.get("text") or value.get("data") or "").strip()
        if text:
            lines.append(f"- {text}")
    if not lines:
        return ""
    return "## Long-term memories\n" + "\n".join(lines)


def _runtime_memory_block(request: ModelRequest) -> str:
    runtime = getattr(request, "runtime", None)
    return _context_field(getattr(runtime, "context", None) if runtime else None, "memory_block")


@dynamic_prompt
def procura_kb_prompt(request: ModelRequest) -> str:
    """Inject ranked project-file excerpts and LTM so create_agent can cite them without tools."""
    base = read_prompt("procura_main_agent.md")
    project_id = _runtime_project_id(request)
    query = _last_user_text(getattr(request, "messages", None))
    kb = knowledge_prompt_block(project_id, query)
    memory = _runtime_memory_block(request)
    parts = [base]
    if kb:
        parts.append(kb)
    if memory:
        parts.append(memory)
    return "\n\n".join(parts)


def _store_from_runtime() -> Any:
    try:
        from langgraph.config import get_store

        return get_store()
    except Exception:
        return None


async def load_memory_block(store: Any, user_id: str, project_id: str, query: str) -> str:
    if store is None:
        return ""
    namespace = memory_namespace(user_id, project_id)
    try:
        hits = await store.asearch(namespace, query=query or None, limit=LTM_LIMIT)
    except Exception:
        log.exception("ltm asearch failed namespace={}", namespace)
        return ""
    return format_memory_block(list(hits or []))


async def maybe_remember(store: Any, user_id: str, project_id: str, text: str) -> None:
    payload = remember_payload(text)
    if store is None or payload is None:
        return
    namespace = memory_namespace(user_id, project_id)
    try:
        await store.aput(namespace, str(uuid.uuid4()), {"text": payload, "data": payload})
        log.info("ltm remembered namespace={}", namespace)
    except Exception:
        log.exception("ltm aput failed namespace={}", namespace)


@lru_cache(maxsize=1)
def get_procura_main_agent():
    from langchain.agents import create_agent

    from ai_brain.core.config import get_llm
    from ai_brain.core.procurement_ai.file_ingest import ingest_chat_tools

    # ChatDatabricks prefers visitor OBO + system.ai Gateway when the
    # forwarded JWT has ai-gateway; otherwise FM serving endpoints.
    return create_agent(
        model=get_llm(),
        tools=ingest_chat_tools(),
        middleware=[procura_kb_prompt],
        context_schema=ProcuraContext,
    )


procura_main_agent = None


@mlflow.trace(name="procura_main_agent", span_type=SpanType.AGENT)
async def main_agent(
    state: dict[str, Any],
    # LangGraph matches this annotation literally; ``RunnableConfig | None``
    # is rejected and config is then never injected.
    config: Optional[RunnableConfig] = None,  # noqa: UP045
) -> dict[str, Any]:
    # LangChain: pass parent RunnableConfig into nested ainvoke so callbacks
    # (MlflowLangchainTracer) and token streaming propagate.
    project_id = project_id_for_agent(state, config)
    user_id = _user_id_from_config(config)
    incoming = conversation_messages(state)
    query = _last_user_text(incoming) or str(state.get("request") or "")
    store = _store_from_runtime()
    await maybe_remember(store, user_id, project_id, query)
    memory_block = await load_memory_block(store, user_id, project_id, query)
    set_current_project_id(project_id or None)
    try:
        result = await get_procura_main_agent().ainvoke(
            {"messages": incoming},
            config=config,
            context=ProcuraContext(
                project_id=project_id,
                user_id=user_id,
                memory_block=memory_block,
            ),
        )
    finally:
        set_current_project_id(None)
    messages = result.get("messages") or []
    last = messages[-1] if messages else None
    text = content_text(getattr(last, "content", "") if last is not None else "")
    new_messages = list(messages[len(incoming) :]) if messages else []
    out: dict[str, Any] = {"procurement": {"main_agent": text}}
    if new_messages:
        out["messages"] = new_messages
    elif last is not None:
        out["messages"] = [last]
    return out
