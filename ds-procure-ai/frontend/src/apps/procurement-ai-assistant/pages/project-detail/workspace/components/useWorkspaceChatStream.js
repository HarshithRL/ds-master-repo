import { useEffect, useReducer, useRef } from "react";

import { apiPostSse } from "../../../../../../services/api";

export const WORKSPACE_PROCUREMENT = Object.freeze({
  mainagent: true,
  deepagent: false,
});

const initialUi = {
  tab: "Chat",
  draft: "",
  status: "idle",
  sendError: null,
  streamText: "",
  thoughts: [],
  thoughtStartedAt: null,
};

function mergeThought(thoughts, next) {
  const kind = next.kind || (next.detail ? "thought" : "step");
  const label = next.label || (kind === "thought" ? "Thought" : "Working");
  const detail = next.detail || "";
  const last = thoughts.at(-1);
  if (kind === "thought" && last?.kind === "thought") {
    return [
      ...thoughts.slice(0, -1),
      { kind: "thought", label: "Thought", detail: detail || last.detail },
    ];
  }
  if (kind === "step" && last?.kind === "step" && last.label === label) {
    return thoughts;
  }
  return [...thoughts, { kind, label, detail }];
}

function chatUiReducer(state, action) {
  switch (action.type) {
    case "set_tab":
      return { ...state, tab: action.tab };
    case "set_draft":
      return { ...state, draft: action.draft };
    case "send_start":
      return {
        ...state,
        draft: "",
        sendError: null,
        status: "sending",
        streamText: "",
        thoughts: [],
        thoughtStartedAt: Date.now(),
      };
    case "token":
      return { ...state, streamText: action.text };
    case "thought":
      return {
        ...state,
        thoughts: mergeThought(state.thoughts, {
          kind: action.kind,
          label: action.label,
          detail: action.detail,
        }),
      };
    case "send_error":
      return { ...state, sendError: action.error, status: "error" };
    case "send_done":
      return {
        ...state,
        status: "idle",
        streamText: "",
        thoughts: [],
        thoughtStartedAt: null,
      };
    default:
      return state;
  }
}

function isAbortError(err) {
  return err?.name === "AbortError";
}

export function useWorkspaceChatStream({
  projectId,
  messages,
  pendingMessage = "",
  onPendingConsumed,
  onMessagesChange,
  onFileProgress,
}) {
  const [ui, dispatch] = useReducer(chatUiReducer, initialUi);
  const abortRef = useRef(null);
  const generationRef = useRef(0);
  const lastPendingSentRef = useRef("");
  const bottomRef = useRef(null);
  const messagesRef = useRef(messages);
  const sendRef = useRef(null);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    lastPendingSentRef.current = "";
    generationRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    return () => {
      generationRef.current += 1;
      abortRef.current?.abort();
    };
  }, [projectId]);

  useEffect(() => {
    if (ui.status !== "sending") {
      return;
    }
    bottomRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [ui.streamText, ui.thoughts, ui.status]);

  async function sendMessage(text, { skipAppend = false } = {}) {
    if (!text || !projectId) {
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const generation = generationRef.current + 1;
    generationRef.current = generation;

    const history = messagesRef.current ?? [];
    const last = history.at(-1);
    const alreadyPresent =
      skipAppend || (last?.role === "user" && last?.text === text);
    const nextMessages = alreadyPresent
      ? history
      : [...history, { role: "user", text }];
    const apiHistory = alreadyPresent ? history.slice(0, -1) : history;
    onMessagesChange?.(nextMessages);
    dispatch({ type: "send_start" });
    const startedAt = Date.now();

    let assembled = "";
    let thoughts = [];
    let failed = false;

    try {
      await apiPostSse(
        `/api/procurement/projects/${projectId}/workspace/chat/stream`,
        {
          message: text,
          history: apiHistory,
          procurement: {
            ...WORKSPACE_PROCUREMENT,
            project_id: projectId,
          },
        },
        (evt) => {
          if (generation !== generationRef.current) {
            return;
          }
          if (evt.type === "token" && evt.text) {
            assembled += evt.text;
            dispatch({ type: "token", text: assembled });
          } else if (evt.type === "thought" || evt.type === "context") {
            thoughts = mergeThought(thoughts, {
              kind: evt.kind,
              label: evt.label || "Thought",
              detail: evt.detail || "",
            });
            dispatch({
              type: "thought",
              kind: evt.kind,
              label: evt.label || "Thought",
              detail: evt.detail || "",
            });
          } else if (evt.type === "done") {
            assembled = evt.text || assembled;
            if (Array.isArray(evt.thoughts) && evt.thoughts.length) {
              thoughts = evt.thoughts;
            }
            dispatch({ type: "token", text: assembled });
          } else if (evt.type === "file_progress") {
            onFileProgress?.({
              file_id: evt.file_id || "",
              filename: evt.filename || "",
              status: evt.status || "",
              chunk_count: evt.chunk_count || 0,
              error: evt.error || "",
            });
          } else if (evt.type === "index_ready") {
            onFileProgress?.({
              type: "index_ready",
              chunk_count: evt.chunk_count || 0,
              index_ready: true,
            });
          } else if (evt.type === "error") {
            failed = true;
            dispatch({
              type: "send_error",
              error: evt.detail || "Agent stream failed.",
            });
          }
        },
        { signal: controller.signal },
      );

      if (generation !== generationRef.current) {
        return;
      }
      if (!failed) {
        onMessagesChange?.([
          ...nextMessages,
          {
            role: "ai",
            text: assembled || "No reply.",
            thoughts,
            thoughtMs: Date.now() - startedAt,
          },
        ]);
        dispatch({ type: "send_done" });
      }
    } catch (err) {
      if (isAbortError(err) || generation !== generationRef.current) {
        return;
      }
      dispatch({
        type: "send_error",
        error: err?.message || "Unable to reach the agent.",
      });
    }
  }

  useEffect(() => {
    sendRef.current = sendMessage;
  });

  useEffect(() => {
    const text = String(pendingMessage || "").trim();
    if (!text) {
      lastPendingSentRef.current = "";
      return;
    }
    if (!projectId || text === lastPendingSentRef.current) {
      return;
    }
    lastPendingSentRef.current = text;
    onPendingConsumed?.();
    void sendRef.current?.(text, { skipAppend: true });
  }, [pendingMessage, projectId, onPendingConsumed]);

  return { ui, dispatch, sendMessage, bottomRef };
}

export default useWorkspaceChatStream;
