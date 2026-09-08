const API_BASE = import.meta.env.DEV
  ? `http://${typeof window !== "undefined" ? window.location.hostname : "127.0.0.1"}:5000`
  : "";

const FLUSH_MS = 500;
const MAX_BATCH = 20;

let queue = [];
let flushTimer = null;
let currentRequestId = null;

function getApiBase() {
  return API_BASE;
}

function setRequestId(requestId) {
  if (requestId) {
    currentRequestId = requestId;
  }
}

function flush() {
  if (!queue.length) {
    return;
  }

  const events = queue.splice(0, MAX_BATCH);
  const body = JSON.stringify({ events });

  fetch(`${getApiBase()}/api/logs`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(currentRequestId ? { "X-Request-Id": currentRequestId } : {}),
    },
    body,
    keepalive: true,
  }).catch(() => {
    /* swallow transport failures */
  });
}

function scheduleFlush() {
  if (flushTimer) {
    return;
  }
  flushTimer = setTimeout(() => {
    flushTimer = null;
    flush();
  }, FLUSH_MS);
}

export function sendClientLog(event) {
  queue.push(event);
  if (queue.length >= MAX_BATCH) {
    if (flushTimer) {
      clearTimeout(flushTimer);
      flushTimer = null;
    }
    flush();
    return;
  }
  scheduleFlush();
}

export { setRequestId, getApiBase };
