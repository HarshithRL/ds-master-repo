import { useState } from "react";
import { MessageSquare, Plus } from "lucide-react";

import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";

import { API_BASE } from "../../../../../../services/api";
import { kbIsBuilding, kbStatusCopy } from "../kbStatus";
import AnalysisRail from "./AnalysisRail";
import ChatAttachMenu from "./ChatAttachMenu";
import ChatMarkdown from "./ChatMarkdown";
import ChatThoughtProcess from "./ChatThoughtProcess";
import { useChatAnalysis } from "./useChatAnalysis";
import { useWorkspaceChatStream } from "./useWorkspaceChatStream";

const CENTER_TABS = [
  "Chat",
  "History",
];

function messageKey(msg, index) {
  const prefix = msg.role === "user" ? "u" : "a";
  const snippet = (msg.text || "").slice(0, 48);
  return `${prefix}-${index}-${snippet}`;
}

const PACK_DOWNLOAD = /\/api\/procurement\/projects\/[0-9a-f-]+\/packs\/(xlsx|ppt)\/download/i;

function packDownload(text) {
  const match = PACK_DOWNLOAD.exec(String(text || ""));
  if (!match) return null;
  const kind = match[1].toLowerCase();
  return {
    href: `${API_BASE}${match[0]}`,
    label: kind === "ppt" ? "Download SteerCo PPT" : "Download comparison workbook",
  };
}

function replyWithoutDownload(text) {
  return String(text || "")
    .replace(/Download:\s*\/api\/procurement\/projects\/[0-9a-f-]+\/packs\/(xlsx|ppt)\/download/gi, "")
    .trim();
}

function ChatAiBody({
  thoughts,
  text,
  streaming = false,
  durationMs = null,
  points,
  sources,
}) {
  const pack = packDownload(text);
  const visible = replyWithoutDownload(text);
  return (
    <div className="ws-chat-ai-body" aria-live={streaming ? "polite" : undefined}>
      <ChatThoughtProcess
        thoughts={thoughts}
        live={streaming}
        durationMs={durationMs}
      />
      <ChatMarkdown text={visible} streaming={streaming} />
      {pack ? (
        <a className="ws-pack-card" href={pack.href}>
          {pack.label}
        </a>
      ) : null}
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

function CenterTabs({ tab, onTab, onNewChat }) {
  return (
    <div className="ws-center-head">
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
      <button
        type="button"
        className="ws-new-chat"
        onClick={onNewChat}
        aria-label="New chat"
        title="New chat"
      >
        <Plus size={16} />
      </button>
    </div>
  );
}

function formatWhen(value) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toLocaleString();
}

function HistoryList({ sessions, activeSessionId, onOpen }) {
  if (!sessions?.length) {
    return (
      <div className="ws-center-placeholder">
        <p>No chats yet. Start one with the new chat button.</p>
      </div>
    );
  }
  return (
    <div className="ws-history">
      {sessions.map((session) => (
        <button
          key={session.id}
          type="button"
          className={session.id === activeSessionId ? "ws-history-item active" : "ws-history-item"}
          onClick={() => onOpen(session)}
        >
          <span className="ws-history-title">{session.title || "New chat"}</span>
          <span className="ws-history-time">{formatWhen(session.updated_at)}</span>
        </button>
      ))}
    </div>
  );
}

const SKILLS = [
  {
    id: "comparison",
    label: "Comparison matrix",
    hint: "BAFO workbook from the shared template",
    prompt: "Create comparison matrix",
  },
  {
    id: "missing",
    label: "What's missing",
    hint: "Gaps against the uploaded RFP",
    prompt: "What's missing",
  },
];

function skillQuery(draft) {
  const match = /(?:^|\s)@([^\s]*)$/.exec(draft || "");
  return match ? match[1].toLowerCase() : null;
}

function ChatComposer({
  draft,
  sending,
  uploading,
  onDraftChange,
  onSend,
  onAddFile,
}) {
  const [picked, setPicked] = useState(null);
  const query = skillQuery(draft);
  const open = query !== null && !sending;
  const skills = SKILLS.filter((skill) => {
    if (!query) return true;
    return (
      skill.label.toLowerCase().includes(query) ||
      skill.id.includes(query)
    );
  });

  function pickSkill(skill) {
    const next = (draft || "").replace(/(?:^|\s)@[^\s]*$/, "").trim();
    onDraftChange(next);
    setPicked(skill);
  }

  function submit(event) {
    if (picked) {
      event.preventDefault();
      const extra = (draft || "").trim();
      const prompt = extra ? `${picked.prompt}. ${extra}` : picked.prompt;
      setPicked(null);
      onDraftChange("");
      onSend({ preventDefault() {}, prompt });
      return;
    }
    onSend(event);
  }

  return (
    <div className="ws-chat-composer-wrap">
      {open ? (
        <div className="ws-skill-menu" role="listbox" aria-label="Skills">
          {skills.length ? (
            skills.map((skill) => (
              <button
                key={skill.id}
                type="button"
                className="ws-skill-item"
                onClick={() => pickSkill(skill)}
              >
                <span className="ws-skill-label">{skill.label}</span>
                <span className="ws-skill-hint">{skill.hint}</span>
              </button>
            ))
          ) : (
            <p className="ws-skill-empty">No matching skill</p>
          )}
        </div>
      ) : null}
      <form className="ws-chat-composer" onSubmit={submit}>
        <ChatAttachMenu
          onAddFile={onAddFile}
          disabled={uploading || sending}
        />
        {picked ? (
          <button
            type="button"
            className="ws-skill-token"
            onClick={() => setPicked(null)}
            title="Remove skill"
          >
            @{picked.label}
          </button>
        ) : null}
        <label className="ws-chat-input-label" htmlFor="ws-chat-input">
          Message
        </label>
        <input
          id="ws-chat-input"
          type="text"
          placeholder={picked ? "Add a note, or Generate" : "Ask about this project, or type @"}
          value={draft}
          onChange={(e) => onDraftChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setPicked(null);
          }}
          disabled={sending}
          autoComplete="off"
          aria-label="Ask about this project"
        />
        <button
          type="submit"
          className="primary-button"
          disabled={sending || (!picked && !draft.trim())}
        >
          {picked ? "Generate" : "Send"}
        </button>
      </form>
    </div>
  );
}


function ChatPanel({
  projectId,
  sessionId = "",
  sessions = [],
  messages,
  userInitial,
  pendingMessage = "",
  onPendingConsumed,
  onMessagesChange,
  onNewChat,
  onOpenSession,
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
    sessionId,
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
    const prompt = (event.prompt || ui.draft || "").trim();
    if (!prompt) return;
    await sendMessage(prompt);
  }

  return (
    <section className="ws-chat">
      <CenterTabs
        tab={ui.tab}
        onTab={(name) => dispatch({ type: "set_tab", tab: name })}
        onNewChat={() => {
          onNewChat?.();
          dispatch({ type: "set_tab", tab: "Chat" });
        }}
      />

      {ui.tab === "Chat" ? (
        <>
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
        </div>
        <div className="ws-chat-dock">
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
          <ChatComposer
            draft={ui.draft}
            sending={sending}
            uploading={uploading}
            onDraftChange={(draft) => dispatch({ type: "set_draft", draft })}
            onSend={handleSend}
            onAddFile={onAddFile}
          />
        </div>
        </>
      ) : ui.tab === "History" ? (
        <HistoryList
          sessions={sessions}
          activeSessionId={sessionId}
          onOpen={(session) => {
            onOpenSession?.(session);
            dispatch({ type: "set_tab", tab: "Chat" });
          }}
        />
      ) : (
        <div className="ws-center-placeholder">
          <p>{ui.tab} view will appear here.</p>
        </div>
      )}
    </section>
  );
}

export default ChatPanel;
