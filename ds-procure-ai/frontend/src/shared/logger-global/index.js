import { sendClientLog, setRequestId } from "./transport.js";

const SERVICE = "frontend";

const LEVELS = {
  debug: 10,
  info: 20,
  warn: 30,
  error: 40,
};

const MIN_LEVEL = import.meta.env.DEV ? LEVELS.debug : LEVELS.info;

function formatPretty(level, module, workflow, message, extra) {
  const wf = workflow || "-";
  const prefix = `[${SERVICE}|${module}|${wf}]`;
  const detail = extra ? ` ${JSON.stringify(extra)}` : "";
  return `${prefix} ${message}${detail}`;
}

function formatJson(level, module, workflow, message, extra) {
  return JSON.stringify({
    time: new Date().toISOString(),
    level,
    service: SERVICE,
    module,
    workflow: workflow || "-",
    request_id: extra?.request_id || "-",
    message,
    ...extra,
  });
}

function shouldShip(level) {
  return level === "warn" || level === "error";
}

function emit(level, module, workflow, message, extra = {}) {
  if (LEVELS[level] < MIN_LEVEL) {
    return;
  }

  const payload = {
    ...extra,
    request_id: extra.request_id,
  };

  if (import.meta.env.DEV) {
    const line = formatPretty(level, module, workflow, message, payload);
    if (level === "error") {
      console.error(line);
    } else if (level === "warn") {
      console.warn(line);
    } else if (level === "debug") {
      console.debug(line);
    } else {
      console.log(line);
    }
  } else {
    const line = formatJson(level, module, workflow, message, payload);
    if (level === "error") {
      console.error(line);
    } else if (level === "warn") {
      console.warn(line);
    } else {
      console.log(line);
    }
  }

  if (!import.meta.env.DEV && shouldShip(level)) {
    sendClientLog({
      level,
      message,
      module,
      workflow,
      request_id: payload.request_id,
      project_id: payload.project_id,
      stack: payload.stack,
      context: payload.context,
    });
  }
}

export function createLogger(module, defaults = {}) {
  const workflow = defaults.workflow;

  return {
    debug(message, extra) {
      emit("debug", module, workflow, message, extra);
    },
    info(message, extra) {
      emit("info", module, workflow, message, extra);
    },
    warn(message, extra) {
      emit("warn", module, workflow, message, extra);
    },
    error(message, extra) {
      emit("error", module, workflow, message, extra);
    },
    bind(context) {
      return createLogger(module, { ...defaults, ...context });
    },
  };
}

export function installGlobalErrorHandlers(logger) {
  window.addEventListener("error", (event) => {
    logger.error(event.message || "window error", {
      stack: event.error?.stack,
      context: {
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
      },
    });
  });

  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason;
    const message =
      reason instanceof Error ? reason.message : String(reason ?? "unhandled rejection");
    logger.error(message, {
      stack: reason instanceof Error ? reason.stack : undefined,
      workflow: "client.unhandledrejection",
    });
  });
}

export { setRequestId };
