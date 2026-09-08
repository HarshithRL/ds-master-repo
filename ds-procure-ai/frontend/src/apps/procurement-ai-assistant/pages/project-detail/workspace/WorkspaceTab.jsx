import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

import { apiGet } from "../../../../../services/api";
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
import StudioPanel from "./components/StudioPanel";
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

function WorkspaceTab({ projectId, onProjectUpdated }) {
  const location = useLocation();
  const fileInputRef = useRef(null);
  const [data, setData] = useState(null);
  const [messages, setMessages] = useState([]);
  const [pendingMessage, setPendingMessage] = useState("");
  const [error, setError] = useState(null);
  const [fileTick, setFileTick] = useState(0);
  const [uploadUi, setUploadUi] = useState({
    uploading: false,
    error: null,
    status: null,
  });
  const [insights, setInsights] = useState(null);
  const [studioOpen, setStudioOpen] = useState(true);
  const [studioTab, setStudioTab] = useState("Evidence");
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
    setData(null);
    setMessages([]);
    setPendingMessage("");
    setError(null);
    setUploadUi({ uploading: false, error: null, status: null });
    setInsights(null);
    apiGet(`/api/procurement/projects/${projectId}/workspace`)
      .then((payload) => {
        setData(payload);
        const seed = seedFromLocation(projectId, location.state);
        if (seed) {
          setMessages(
            seed.messages.map((msg) => ({
              role: msg.role,
              text: msg.text,
            })),
          );
          setPendingMessage(seed.pendingMessage || "");
        } else {
          setMessages(payload.chatMessages ?? []);
        }
      })
      .catch(() => setError("Unable to load workspace."));
  }, [projectId, location.state]);

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
    <div className={studioOpen ? "workspace-tab" : "workspace-tab studio-collapsed"}>
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
        fileStatus={fileProgress}
      />
      <ChatPanel
        projectId={projectId}
        messages={messages}
        userInitial={data.userInitial}
        pendingMessage={pendingMessage}
        onPendingConsumed={consumePending}
        onMessagesChange={setMessages}
        onProjectUpdated={onProjectUpdated}
        onAddFile={openFilePicker}
        uploading={uploadUi.uploading}
        uploadError={uploadUi.error}
        uploadStatus={uploadUi.status}
        analysisRefresh={fileTick}
        onInsights={handleInsights}
        onFileProgress={handleFileProgress}
      />
      {studioOpen ? (
        <StudioPanel
          projectName={data.projectName}
          graph={data.graph}
          insights={insights}
          tab={studioTab}
          onTab={setStudioTab}
          onCollapse={() => setStudioOpen(false)}
        />
      ) : (
        <button type="button" className="ws-studio-rail" onClick={() => setStudioOpen(true)}>
          Studio
        </button>
      )}
    </div>
  );
}

export default WorkspaceTab;
