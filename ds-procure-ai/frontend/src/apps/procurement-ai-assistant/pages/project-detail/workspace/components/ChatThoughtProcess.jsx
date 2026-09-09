import { ChevronRight } from "lucide-react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

function thoughtKey(item, index) {
  return `${item.kind ?? "step"}-${item.label ?? "item"}-${index}`;
}

function formatThoughtSummary(live, durationMs) {
  if (live) {
    return { title: "Thinking", duration: "" };
  }
  if (durationMs == null) {
    return { title: "Thought", duration: "" };
  }
  if (durationMs < 1200) {
    return { title: "Thought briefly", duration: "" };
  }
  const seconds = Math.round(durationMs / 1000);
  return { title: "Thought", duration: `${seconds}s` };
}

function ChatThoughtProcess({ thoughts, live = false, durationMs = null }) {
  const items = Array.isArray(thoughts) ? thoughts : [];
  const reasoning = items.find((item) => item.kind === "thought" && item.detail);
  const steps = items.filter((item) => item.kind === "step" && item.label);
  const hasBody = steps.length > 0 || Boolean(reasoning?.detail);

  if (!live && !hasBody) {
    return null;
  }

  const summary = formatThoughtSummary(live, durationMs);

  if (!hasBody) {
    return (
      <div className="ws-trace" aria-live="polite">
        <span className="ws-trace-summary">
          {summary.title}
          <span className="ws-trace-dots" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
        </span>
      </div>
    );
  }

  return (
    <Collapsible defaultOpen={live} className="ws-trace">
      <CollapsibleTrigger
        className="ws-trace-trigger"
        aria-label={
          summary.duration
            ? `${summary.title} ${summary.duration}`
            : summary.title
        }
      >
        <ChevronRight className="ws-trace-chevron" aria-hidden="true" />
        <span className="ws-trace-title">{summary.title}</span>
        {summary.duration ? (
          <span className="ws-trace-duration">{summary.duration}</span>
        ) : live ? (
          <span className="ws-trace-dots" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
        ) : null}
      </CollapsibleTrigger>
      <CollapsibleContent className="ws-trace-panel">
        <ul className="ws-trace-list">
          {steps.map((step, index) => (
            <li key={thoughtKey(step, index)} className="ws-trace-step">
              {step.label}
            </li>
          ))}
          {reasoning?.detail ? (
            <li className="ws-trace-reasoning">{reasoning.detail}</li>
          ) : null}
        </ul>
      </CollapsibleContent>
    </Collapsible>
  );
}

export default ChatThoughtProcess;
