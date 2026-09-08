import { useState } from "react";
import { MessageSquare } from "lucide-react";

import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";

import { kbIsBuilding, kbStatusCopy } from "../kbStatus";
import AnalysisRail from "./AnalysisRail";
import ChatAttachMenu from "./ChatAttachMenu";
import ChatMarkdown from "./ChatMarkdown";
import ChatThoughtProcess from "./ChatThoughtProcess";
import { useChatAnalysis } from "./useChatAnalysis";
import { useWorkspaceChatStream } from "./useWorkspaceChatStream";

const CENTER_TABS = [
  "Chat",
  "Document",
  "Spreadsheet",
  "Presentation",
  "Preview",
];

function messageKey(msg, index) {
  const prefix = msg.role === "user" ? "u" : "a";
  const snippet = (msg.text || "").slice(0, 48);
  return `${prefix}-${index}-${snippet}`;
}

function ChatAiBody({
  thoughts,
  text,
  streaming = false,
  durationMs = null,
  points,
  sources,
}) {
  return (
    <div className="ws-chat-ai-body" aria-live={streaming ? "polite" : undefined}>
      <ChatThoughtProcess
        thoughts={thoughts}
        live={streaming}
        durationMs={durationMs}
      />
      <ChatMarkdown text={text} streaming={streaming} />
      {points ? (
        <ul>
          {points.map((point) => (
            <li key={point}>{point}</li>
          ))}
        </ul>
      ) : null}
      {sources ? (
        <div className="ws-sources">
          {sources.map((source) => (
            <span key={source}>{source}</span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function CenterTabs({ tab, onTab }) {
  return (
    <div className="ws-center-tabs">
      {CENTER_TABS.map((name) => (
        <button
          key={name}
          type="button"
          className={tab === name ? "active" : ""}
          onClick={() => onTab(name)}
        >
          {name}
        </button>
      ))}
    </div>
  );
}

function ChatComposer({
  draft,
  sending,
  uploading,
  onDraftChange,
  onSend,
  onAddFile,
}) {
  return (
    <form className="ws-chat-composer" onSubmit={onSend}>
      <ChatAttachMenu
        onAddFile={onAddFile}
        disabled={uploading || sending}
      />
      <label className="ws-chat-input-label" htmlFor="ws-chat-input">
        Message
      </label>
      <input
        id="ws-chat-input"
        type="text"
        placeholder="Ask about this project…"
        value={draft}
        onChange={(e) => onDraftChange(e.target.value)}
        disabled={sending}
        autoComplete="off"
        aria-label="Ask about this project"
      />
      <button
        type="submit"
        className="primary-button"
        disabled={sending || !draft.trim()}
      >
        Send
      </button>
    </form>
  );
}

function ChatPanel({
  projectId,
  messages,
  userInitial,
  pendingMessage = "",
  onPendingConsumed,
  onMessagesChange,
  onAddFile,
  uploading = false,
  uploadError = null,
  uploadStatus = null,
  analysisRefresh = 0,
  onInsights,
  onFileProgress,
}) {
  const { ui, dispatch, sendMessage, bottomRef } = useWorkspaceChatStream({
    projectId,
    messages,
    pendingMessage,
    onPendingConsumed,
    onMessagesChange,
    onFileProgress,
  });
  const analysis = useChatAnalysis(projectId, {
    refreshToken: analysisRefresh,
    onInsights,
  });
  const [analysisOpen, setAnalysisOpen] = useState(false);
  const sending = ui.status === "sending";
  const insights = analysis.insights;
  const kbStatus = insights?.kb_status;
  const kbMessage = insights?.kb_message;

  const hasMessages = (messages ?? []).length > 0;
  const buildingKb = kbIsBuilding(kbStatus) || uploading;
  const kbFailed = kbStatus === "failed";
  const kbCopy = kbStatusCopy(kbStatus, kbMessage);
  const statusText = buildingKb
    ? kbCopy || uploadStatus || "Building knowledge base…"
    : kbCopy || uploadStatus;

  async function handleSend(event) {
    event.preventDefault();
    await sendMessage(ui.draft.trim());
  }

  return (
    <section className="ws-chat">
      <CenterTabs
        tab={ui.tab}
        onTab={(name) => dispatch({ type: "set_tab", tab: name })}
      />

      {ui.tab === "Chat" ? (
        <div className="ws-chat-content">
          <AnalysisRail
            open={analysisOpen}
            onOpenChange={setAnalysisOpen}
            insights={insights}
            error={analysis.error}
            skippedGaps={analysis.skippedGaps}
            busy={analysis.busy}
            onSkipGaps={analysis.skipGaps}
            onBuild={analysis.buildPack}
            onAddFile={onAddFile}
            downloadPath={analysis.downloadPath}
          />
          {!hasMessages && !sending ? (
            <Empty className="ws-chat-empty">
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <MessageSquare />
                </EmptyMedia>
                <EmptyTitle>Ask about this project</EmptyTitle>
                <EmptyDescription>
                  Send a question to the procurement agent. Replies stream in
                  here.
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : null}

          {(messages ?? []).map((msg, index) =>
            msg.role === "user" ? (
              <div key={messageKey(msg, index)} className="ws-chat-user">
                <div className="ws-avatar">{userInitial}</div>
                <div className="ws-chat-bubble">{msg.text}</div>
              </div>
            ) : (
              <div key={messageKey(msg, index)} className="ws-chat-ai">
                <div className="ws-ai-avatar">AI</div>
                <ChatAiBody
                  thoughts={msg.thoughts}
                  text={msg.text}
                  durationMs={msg.thoughtMs}
                  points={msg.points}
                  sources={msg.sources}
                />
              </div>
            ),
          )}

          {sending ? (
            <div className="ws-chat-ai">
              <div className="ws-ai-avatar">AI</div>
              <ChatAiBody
                thoughts={ui.thoughts}
                text={ui.streamText}
                streaming
              />
            </div>
          ) : null}

          <div ref={bottomRef} />

          <ChatComposer
            draft={ui.draft}
            sending={sending}
            uploading={uploading}
            onDraftChange={(draft) => dispatch({ type: "set_draft", draft })}
            onSend={handleSend}
            onAddFile={onAddFile}
          />
          {buildingKb ? (
            <p className="flex items-center gap-2 text-muted-foreground text-xs" role="status">
              <Spinner />
              <span>{statusText}</span>
            </p>
          ) : null}
          {kbFailed && statusText && !buildingKb ? (
            <p className="ws-chat-error" role="alert">
              {statusText}
            </p>
          ) : null}
          {statusText && !uploadError && !buildingKb && !kbFailed ? (
            <p className="ws-chat-upload-status" role="status">
              {statusText}
            </p>
          ) : null}
          {uploadError ? (
            <p className="ws-chat-error" role="alert">
              {uploadError}
            </p>
          ) : null}
          {ui.sendError ? (
            <p className="ws-chat-error" role="alert">
              {ui.sendError}
            </p>
          ) : null}
        </div>
      ) : (
        <div className="ws-center-placeholder">
          <p>{ui.tab} view will appear here.</p>
        </div>
      )}
    </section>
  );
}

export default ChatPanel;
