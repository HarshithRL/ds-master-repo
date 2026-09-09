import { Spinner } from "@/components/ui/spinner";

function fileStatusLabel(status) {
  if (status === "failed" || status === "error") return "failed";
  if (status === "chunked" || status === "ok" || status === "parsed" || status === "ready") return "parsed";
  if (status === "pending") return "queued";
  return "";
}

function FileExplorer({ files, storage, onAddFile, uploading = false, kbBuilding = false, fileStatus = {} }) {
  return (
    <aside className="ws-files">
      <div className="ws-panel-header">
        <strong className="flex items-center gap-2">
          PROJECT FILES
          {kbBuilding || uploading ? <Spinner /> : null}
        </strong>
        <button
          type="button"
          aria-label="Add file"
          onClick={onAddFile}
          disabled={uploading || !onAddFile}
        >
          ＋
        </button>
      </div>

      <div className="ws-file-search">
        <span aria-hidden="true">⌕</span>
        <input type="text" placeholder="Search files..." />
      </div>

      <div className="ws-file-list">
        <div className="ws-file-section">
          <div className="ws-file-section-title">
            INPUTS
            <span>{files.inputsCount}</span>
          </div>
          {files.inputs.map((group) => (
            <div key={group.folder} className="ws-file-folder-block">
              <div className="ws-file-folder">📁 {group.folder}</div>
              {group.files.map((name) => {
                const status = fileStatusLabel(fileStatus[name] || files.statuses?.[name]);
                return (
                <button key={name} type="button" className="ws-file-item">
                  <span className="ws-file-name">{name}</span>
                  {status ? <span className={"ws-file-status is-" + status}>{status}</span> : null}
                </button>
                );
              })}
            </div>
          ))}
        </div>

        <div className="ws-file-section">
          <div className="ws-file-section-title">
            AI GENERATED
            <span>{files.generated.length}</span>
          </div>
          {files.generated.map((name) => (
            <button key={name} type="button" className="ws-file-item">
              {name}
            </button>
          ))}
        </div>

        <div className="ws-file-section">
          <div className="ws-file-section-title">
            ARTIFACTS
            <span>{files.artifacts.length}</span>
          </div>
          {files.artifacts.map((name) => (
            <div key={name} className="ws-artifact-item">
              📁 {name}
            </div>
          ))}
        </div>
      </div>

      <div className="ws-storage">
        <span>Storage used</span>
        <strong>{storage.label}</strong>
        <div className="ws-storage-bar">
          <span style={{ width: `${storage.percent}%` }} />
        </div>
      </div>
    </aside>
  );
}

export default FileExplorer;
