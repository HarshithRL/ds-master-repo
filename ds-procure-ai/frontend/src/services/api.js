import { createLogger, setRequestId } from "../shared/logger-global/index.js";

const log = createLogger("services.api");

function localApiHost() {
  return typeof window !== "undefined" ? window.location.hostname : "127.0.0.1";
}

export const API_BASE = import.meta.env.DEV ? `http://${localApiHost()}:5000` : "";
const FETCH_OPTS = { credentials: "include" };

function captureRequestId(response) {
  const requestId = response.headers.get("X-Request-Id");
  if (requestId) {
    setRequestId(requestId);
  }
  return response;
}

function logRequestFailure(method, path, status, detail) {
  log.error("API request failed", {
    workflow: "http.client",
    context: { method, path, status, detail },
  });
}

export async function apiGet(path) {
  const response = await fetch(`${API_BASE}${path}`, FETCH_OPTS).then(captureRequestId);

  if (!response.ok) {
    logRequestFailure("GET", path, response.status);
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json();
}

export async function apiPost(path, body) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  }).then(captureRequestId);

  if (!response.ok) {
    let detail = `Request failed: ${response.status}`;
    try {
      const errBody = await response.json();
      if (errBody?.detail) {
        detail = errBody.detail;
      } else if (errBody?.error) {
        detail = errBody.error;
      }
    } catch {
      /* ignore parse errors */
    }
    logRequestFailure("POST", path, response.status, detail);
    throw new Error(detail);
  }

  return response.json();
}

/**
 * POST multipart form data.
 */
export async function apiPostForm(path, formData) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    credentials: "include",
    body: formData,
  }).then(captureRequestId);

  if (!response.ok) {
    let detail = `Request failed: ${response.status}`;
    try {
      const errBody = await response.json();
      if (errBody?.detail) {
        detail = errBody.detail;
      } else if (errBody?.error) {
        detail = errBody.error;
      }
    } catch {
      /* ignore parse errors */
    }
    logRequestFailure("POST", path, response.status, detail);
    throw new Error(detail);
  }

  return response.json();
}

function dispatchSseFrame(rawEvent, onEvent) {
  let eventType = "message";
  const dataLines = [];
  for (const line of rawEvent.split("\n")) {
    if (line.startsWith("event:")) {
      eventType = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }
  if (!dataLines.length) {
    return;
  }
  try {
    const payload = JSON.parse(dataLines.join("\n"));
    onEvent?.({ type: eventType, ...payload });
  } catch {
    onEvent?.({ type: eventType, raw: dataLines.join("\n") });
  }
}

/**
 * POST and consume SSE (`text/event-stream`).
 * Calls `onEvent({ type, ...payload })` for each frame.
 * Accepts both LF and CRLF separators (sse-starlette defaults to CRLF).
 * Pass `signal` from AbortController to cancel the stream.
 */
export async function apiPostSse(
  path,
  body,
  onEvent,
  { base = API_BASE, signal } = {},
) {
  const response = await fetch(`${base}${path}`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(body ?? {}),
    signal,
  }).then(captureRequestId);

  if (!response.ok) {
    let detail = `Request failed: ${response.status}`;
    try {
      const errBody = await response.json();
      if (errBody?.detail) {
        detail = errBody.detail;
      } else if (errBody?.error) {
        detail = errBody.error;
      }
    } catch {
      /* ignore */
    }
    logRequestFailure("POST", path, response.status, detail);
    throw new Error(detail);
  }

  if (!response.body) {
    throw new Error("Streaming not supported by this browser.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  function drainFrames() {
    buffer = buffer.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    let sep;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const rawEvent = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      if (!signal?.aborted) {
        dispatchSseFrame(rawEvent, onEvent);
      }
    }
  }

  try {
    while (true) {
      if (signal?.aborted) {
        await reader.cancel();
        throw new DOMException("Aborted", "AbortError");
      }
      const { done, value } = await reader.read();
      if (done) {
        buffer += decoder.decode();
        drainFrames();
        if (buffer.trim() && !signal?.aborted) {
          dispatchSseFrame(buffer, onEvent);
        }
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      drainFrames();
    }
  } catch (err) {
    if (err?.name === "AbortError") {
      try {
        await reader.cancel();
      } catch {
        /* already closed */
      }
      throw err;
    }
    throw err;
  }
}
