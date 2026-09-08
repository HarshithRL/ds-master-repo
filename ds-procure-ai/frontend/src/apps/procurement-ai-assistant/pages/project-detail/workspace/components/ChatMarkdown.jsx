import { useDeferredValue } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

function ChatMarkdown({ text, streaming = false }) {
  const deferred = useDeferredValue(text ?? "");
  const source = streaming ? deferred : (text ?? "");

  if (!source) {
    return null;
  }

  return (
    <div className="ws-md">
      <Markdown remarkPlugins={[remarkGfm]}>{source}</Markdown>
      {streaming ? <span className="ws-stream-caret" aria-hidden="true" /> : null}
    </div>
  );
}

export default ChatMarkdown;
