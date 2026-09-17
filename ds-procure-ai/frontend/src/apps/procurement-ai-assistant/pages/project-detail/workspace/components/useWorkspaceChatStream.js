import { useEffect, useReducer, useRef } from "react";

import { apiGetSse, apiPost } from "../../../../../../services/api";

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
  responseId: null,
  sequenceNumber: 0,
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
        responseId: action.responseId || null,
        sequenceNumber: 0,
      };
    case "token":
      return { ...state, streamText: action.text, sequenceNumber: action.sequenceNumber ?? state.sequenceNumber };
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
  sessionId = "",
  messages,
  pendingMessage = "",
  onPendingConsumed,
  onMessagesChange,
  onFileProgress,
  onSession,
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
  }, [projectId, sessionId]);

  useEffect(() => {
    if (ui.status !== "sending") {
      return;
    }
    bottomRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [ui.streamText, ui.thoughts, ui.status]);

  async function sendMessage(text, { skipAppend = false } = {}) {
    if (!text || !projectId || !sessionId) {
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
      const response = await apiPost(
        `/api/procurement/projects/${projectId}/workspace/responses`,
        { message: text, session_id: sessionId, history: apiHistory },
      );
      if (!response?.id) throw new Error("Agent did not create a background response.");
      dispatch({ type: "send_start", responseId: response.id });
      let lastSequence = 0;
      await apiGetSse(
        `/api/procurement/projects/${projectId}/workspace/responses/${response.id}/events?starting_after=0`,
        (evt) => {
          if (generation !== generationRef.current) {
            return;
          }
          lastSequence = Math.max(lastSequence, Number(evt.sequence_number || 0));
          if (evt.type === "response.output_text.delta" && evt.custom_outputs?.kind === "thought") {
            thoughts = mergeThought(thoughts, {
              kind: "thought",
              label: "Thought",
              detail: evt.delta || "",
            });
            dispatch({
              type: "thought",
              kind: "thought",
              label: "Thought",
              detail: evt.delta || "",
            });
          } else if (evt.type === "response.output_text.delta" && evt.delta) {
            assembled += evt.delta;
            dispatch({ type: "token", text: assembled, sequenceNumber: lastSequence });
          } else if (evt.type === "response.output_item.done") {
            const item = evt.item || {};
            const content = Array.isArray(item.content) ? item.content : [];
            const textPart = content.map((part) => part?.text || "").join("");
            assembled = textPart || assembled;
            dispatch({ type: "token", text: assembled, sequenceNumber: lastSequence });
          } else if (evt.type === "response.resumed") {
            dispatch({ type: "thought", kind: "step", label: "Resumed safely", detail: "Continuing a recovered agent run." });
          } else if (evt.custom_outputs?.kind === "file_progress") {
            onFileProgress?.({
              ...evt.custom_outputs,
            });
          } else if (evt.type === "error") {
            failed = true;
            dispatch({
              type: "send_error",
              error: evt.error?.message || "Agent stream failed.",
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
    if (!projectId || !sessionId || text === lastPendingSentRef.current) {
      return;
    }
    lastPendingSentRef.current = text;
    onPendingConsumed?.();
    void sendRef.current?.(text, { skipAppend: true });
  }, [pendingMessage, projectId, sessionId, onPendingConsumed]);

  return { ui, dispatch, sendMessage, bottomRef };
}

export default useWorkspaceChatStream;
