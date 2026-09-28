import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

import { apiGet, apiPost } from "../../../../../services/api";
import {
  markIntakePendingSent,
  readIntakeSeed,
  uploadFilesTrigger,
  wasIntakePendingSent,
} from "../../new-project/intakeChat";
import {
  FILE_ACCEPT,
  addStagedFiles,
} from "../../new-project/stagedFiles";
import {
  summarizeUploadResult,
  uploadProjectFiles,
} from "../../new-project/uploadProjectFiles";
import { kbIsBuilding } from "./kbStatus";
import FileExplorer from "./components/FileExplorer";
import ChatPanel from "./components/ChatPanel";
import "./workspace-tab.css";

function seedFromLocation(projectId, locationState) {
  const pendingAlreadySent = wasIntakePendingSent(projectId);
  const hasNavSeed =
    locationState != null &&
    (Array.isArray(locationState.intakeMessages) ||
      Boolean(locationState.pendingMessage));
  if (hasNavSeed) {
    return {
      messages: Array.isArray(locationState.intakeMessages)
        ? locationState.intakeMessages
        : [],
      pendingMessage: pendingAlreadySent
        ? ""
        : locationState.pendingMessage || "",
    };
  }
  const stored = readIntakeSeed(projectId);
  if (
    stored &&
    (Array.isArray(stored.messages) || Boolean(stored.pendingMessage))
  ) {
    return {
      messages: Array.isArray(stored.messages) ? stored.messages : [],
      pendingMessage: pendingAlreadySent ? "" : stored.pendingMessage || "",
    };
  }
  return null;
}

function sessionStorageKey(projectId) {
  return `nexus-chat-session:${projectId}`;
}

function WorkspaceTab({ projectId, onProjectUpdated }) {
  const location = useLocation();
  const fileInputRef = useRef(null);
  const [data, setData] = useState(null);
  const [messages, setMessages] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [sessionId, setSessionId] = useState("");
  const [pendingMessage, setPendingMessage] = useState("");
  const [error, setError] = useState(null);
  const [fileTick, setFileTick] = useState(0);
  const [uploadUi, setUploadUi] = useState({
    uploading: false,
    error: null,
    status: null,
  });
  const [indexing, setIndexing] = useState(false);
  const [insights, setInsights] = useState(null);
  const [fileProgress, setFileProgress] = useState({});

  const handleFileProgress = useCallback((evt) => {
    if (!evt || evt.type === "index_ready" || evt.index_ready) {
      return;
    }
    const name = String(evt.filename || "").trim();
    if (!name) {
      return;
    }
    setFileProgress((prev) => ({ ...prev, [name]: evt.status || "pending" }));
  }, []);

  const handleInsights = useCallback((payload) => {
    setInsights(payload);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setMessages([]);
    setSessions([]);
    setSessionId("");
    setPendingMessage("");
    setError(null);
    setUploadUi({ uploading: false, error: null, status: null });
    setInsights(null);

    async function load() {
      const payload = await apiGet(`/api/procurement/projects/${projectId}/workspace`);
      if (cancelled) {
        return;
      }
      setData(payload);
      const seed = seedFromLocation(projectId, location.state);
      let rows = [];
      try {
        const listed = await apiGet(
          `/api/procurement/projects/${projectId}/workspace/sessions`,
        );
        rows = listed.sessions ?? [];
      } catch {
        rows = [];
      }
      if (!rows.length) {
        const created = await apiPost(
          `/api/procurement/projects/${projectId}/workspace/sessions`,
          {},
        );
        rows = [created];
      }
      if (cancelled) {
        return;
      }
      setSessions(rows);
      const stored = sessionStorage.getItem(sessionStorageKey(projectId));
      const current = rows.find((row) => row.id === stored) || rows[0];
      setSessionId(current.id);
      sessionStorage.setItem(sessionStorageKey(projectId), current.id);
      if (seed) {
        setMessages(
          seed.messages.map((msg) => ({
            role: msg.role,
            text: msg.text,
          })),
        );
        setPendingMessage(seed.pendingMessage || "");
        return;
      }
      const detail = await apiGet(
        `/api/procurement/projects/${projectId}/workspace/sessions/${current.id}`,
      );
      if (cancelled) {
        return;
      }
      setMessages(detail.messages ?? []);
    }

    load().catch(() => {
      if (!cancelled) {
        setError("Unable to load workspace.");
      }
    });
    return () => {
      cancelled = true;
    };
  }, [projectId, location.state]);

  async function refreshSessions() {
    const listed = await apiGet(
      `/api/procurement/projects/${projectId}/workspace/sessions`,
    );
    setSessions(listed.sessions ?? []);
  }

  async function startNewChat() {
    const created = await apiPost(
      `/api/procurement/projects/${projectId}/workspace/sessions`,
      {},
    );
    setSessions((prev) => [created, ...prev.filter((item) => item.id !== created.id)]);
    setSessionId(created.id);
    sessionStorage.setItem(sessionStorageKey(projectId), created.id);
    setMessages([]);
    setPendingMessage("");
  }

  async function openSession(session) {
    const detail = await apiGet(
      `/api/procurement/projects/${projectId}/workspace/sessions/${session.id}`,
    );
    setSessionId(detail.id);
    sessionStorage.setItem(sessionStorageKey(projectId), detail.id);
    setMessages(detail.messages ?? []);
    setPendingMessage("");
  }

  function consumePending() {
    setPendingMessage("");
    markIntakePendingSent(projectId);
  }

  function refreshFiles() {
    return apiGet(`/api/procurement/projects/${projectId}/workspace`).then((payload) => {
      setData((prev) =>
        prev
          ? { ...prev, files: payload.files, storage: payload.storage }
          : payload,
      );
      setFileTick((n) => n + 1);
      onProjectUpdated?.();
    });
  }

  function openFilePicker() {
    if (uploadUi.uploading) {
      return;
    }
    fileInputRef.current?.click();
  }

  async function rebuildIndex() {
    if (indexing) {
      return;
    }
    setIndexing(true);
    try {
      // Same contract as the Analysis rail's "keep my edits" button: an
      // explicit false stops the two paths drifting into different defaults.
      const result = await apiPost(`/api/procurement/projects/${projectId}/packs/kb`, {
        clear_reviews: false,
      });
      if (result?.procurement?.kb_already_running) {
        setUploadUi((prev) => ({
          ...prev,
          error:
            "A knowledge base build is already running for this project. " +
            "Wait for it to finish before starting another.",
        }));
      }
      setFileTick((tick) => tick + 1);
    } catch (err) {
      setUploadUi((prev) => ({
        ...prev,
        error: err?.message || "Index rebuild failed.",
      }));
    } finally {
      setIndexing(false);
    }
  }

  async function handleFilesSelected(event) {
    const incoming = Array.from(event.target.files || []);
    event.target.value = "";
    const { files, errors } = addStagedFiles([], incoming);
    if (errors.length) {
      setUploadUi({
        uploading: false,
        error: errors.join(" "),
        status: null,
      });
      return;
    }
    if (!files.length) {
      return;
    }

    setUploadUi({ uploading: true, error: null, status: "Uploading\u2026" });
    try {
      const result = await uploadProjectFiles(projectId, files);
      try {
        await refreshFiles();
      } catch {
        setFileTick((n) => n + 1);
      }
      setUploadUi({
        uploading: false,
        error: null,
        status: `${summarizeUploadResult(result.uploaded)}. Building knowledge base…`,
      });
      setPendingMessage(uploadFilesTrigger(result.uploaded));
    } catch (err) {
      setUploadUi({
        uploading: false,
        error: err?.message || "Unable to upload files.",
        status: null,
      });
    }
  }


  const kbBuilding = kbIsBuilding(insights?.kb_status) || uploadUi.uploading;

  if (!data && !error) {
    return <div className="workspace-tab">Loading\u2026</div>;
  }

  if (error || !data) {
    return (
      <div className="workspace-tab">{error ?? "Workspace unavailable."}</div>
    );
  }

  return (
    <div className="workspace-tab studio-collapsed">
      <input
        ref={fileInputRef}
        id="ws-project-file-input"
        type="file"
        accept={FILE_ACCEPT}
        multiple
        hidden
        onChange={handleFilesSelected}
      />
      <FileExplorer
        files={data.files}
        storage={data.storage}
        uploading={uploadUi.uploading}
        kbBuilding={kbBuilding}
        onAddFile={openFilePicker}
        onIndex={rebuildIndex}
        indexing={indexing}
        fileStatus={fileProgress}
      />
      <ChatPanel
        projectId={projectId}
        sessionId={sessionId}
        sessions={sessions}
        messages={messages}
        userInitial={data.userInitial}
        pendingMessage={pendingMessage}
        onPendingConsumed={consumePending}
        onMessagesChange={(next) => {
          setMessages(next);
          refreshSessions().catch(() => {});
        }}
        onNewChat={startNewChat}
        onOpenSession={openSession}
        onProjectUpdated={onProjectUpdated}
        onAddFile={openFilePicker}
        uploading={uploadUi.uploading}
        uploadError={uploadUi.error}
        uploadStatus={uploadUi.status}
        analysisRefresh={fileTick}
        onInsights={handleInsights}
        onFileProgress={handleFileProgress}
      />
    </div>
  );
}

export default WorkspaceTab;
