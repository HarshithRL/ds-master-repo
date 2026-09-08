import { useEffect, useState } from "react";
import { apiGet } from "../../../../../services/api";
import "./documents-tab.css";

function FileRow({ name, type, meta }) {
  return (
    <div className="file-row">
      <span className={`file-icon ${type}`}>{type.toUpperCase()}</span>
      <div className="file-info">
        <strong>{name}</strong>
        <span>{meta}</span>
      </div>
      <span className="file-action">⋯</span>
    </div>
  );
}

function DocumentsTab({ projectId }) {
  const [fileGroups, setFileGroups] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setFileGroups(null);
    setError(null);
    apiGet(`/api/procurement/projects/${projectId}/documents`)
      .then((data) => setFileGroups(data.fileGroups))
      .catch(() => setError("Unable to load documents."));
  }, [projectId]);

  if (!fileGroups && !error) {
    return <section className="documents-tab">Loading…</section>;
  }

  if (error || !fileGroups) {
    return (
      <section className="documents-tab">
        {error ?? "Documents unavailable."}
      </section>
    );
  }

  return (
    <section className="documents-tab">
      <div className="section-header">
        <div>
          <span className="section-eyebrow">DOCUMENTS</span>
          <h2>Project Files</h2>
          <p>Documents associated with this procurement project.</p>
        </div>
        <button type="button" className="primary-button">
          ✦ New AI Task
        </button>
      </div>

      <div className="file-search">
        <span aria-hidden="true">⌕</span>
        <input type="text" placeholder="Search files..." />
      </div>

      {fileGroups.map((group) => (
        <div key={group.title} className="file-group">
          <h3>{group.title}</h3>
          <div className="file-list">
            {group.files.map((file) => (
              <FileRow key={file.name} {...file} />
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}

export default DocumentsTab;
