import { useCallback, useEffect, useMemo, useState } from "react";
import { apiGet, apiPatch } from "../../../../../services/api";
import "./documents-tab.css";

function VendorEditor({ file, options, onSave, onCancel }) {
  const [value, setValue] = useState(file.vendorId || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save(event) {
    event.preventDefault();
    const next = value.trim();
    if (!next) {
      setError("Vendor is required.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await onSave(next);
    } catch (err) {
      setError(err.message || "Could not save.");
      setBusy(false);
    }
  }

  return (
    <form className="file-vendor-editor" onSubmit={save}>
      <input
        autoFocus
        list="known-vendors"
        value={value}
        disabled={busy}
        placeholder="e.g. sap"
        onChange={(event) => setValue(event.target.value)}
      />
      <datalist id="known-vendors">
        {options.map((option) => (
          <option key={option} value={option} />
        ))}
      </datalist>
      <button type="submit" disabled={busy}>
        {busy ? "Saving…" : "Save"}
      </button>
      <button type="button" className="is-ghost" disabled={busy} onClick={onCancel}>
        Cancel
      </button>
      {error ? <span className="file-vendor-error">{error}</span> : null}
    </form>
  );
}

function FileRow({ file, options, editing, onEdit, onCancel, onSave }) {
  const { name, type, meta, href } = file;
  const unreadable = file.parseStatus === "error" || file.parseStatus === "pending";
  const needsVendor = file.vendorGuessed || (unreadable && !file.vendorManual);

  return (
    <div className={`file-row${needsVendor ? " needs-vendor" : ""}`}>
      <span className={`file-icon ${type}`}>{type.toUpperCase()}</span>
      <div className="file-info">
        <strong>{name}</strong>
        <span>{meta}</span>
        {editing ? (
          <VendorEditor
            file={file}
            options={options}
            onSave={onSave}
            onCancel={onCancel}
          />
        ) : (
          file.vendorLabel && (
            <span className="file-vendor-line">
              <button
                type="button"
                className={`file-vendor-chip${needsVendor ? " is-guess" : ""}${
                  file.vendorManual ? " is-manual" : ""
                }`}
                onClick={onEdit}
                title="Set the bidder for this file"
              >
                {file.vendorLabel}
                {file.vendorManual ? " ✓" : ""}
              </button>
              {needsVendor ? (
                <span className="file-vendor-warn">
                  {unreadable
                    ? "Could not read this file — vendor is a filename guess"
                    : "Vendor guessed from the filename"}
                </span>
              ) : null}
            </span>
          )
        )}
      </div>
      {href ? (
        <a className="file-action" href={href} download>
          Download
        </a>
      ) : (
        <span className="file-action">⋯</span>
      )}
    </div>
  );
}

function DocumentsTab({ projectId }) {
  const [fileGroups, setFileGroups] = useState(null);
  const [error, setError] = useState(null);
  const [editingId, setEditingId] = useState("");
  const [changed, setChanged] = useState(0);

  const load = useCallback(
    () =>
      apiGet(`/api/procurement/projects/${projectId}/documents`)
        .then((data) => setFileGroups(data.fileGroups))
        .catch(() => setError("Unable to load documents.")),
    [projectId],
  );

  useEffect(() => {
    setFileGroups(null);
    setError(null);
    setEditingId("");
    setChanged(0);
    load();
  }, [projectId, load]);

  const vendorOptions = useMemo(() => {
    const seen = new Set();
    (fileGroups || []).forEach((group) =>
      (group.files || []).forEach((file) => {
        if (file.vendorId && !file.vendorGuessed) seen.add(file.vendorId);
      }),
    );
    return [...seen].sort();
  }, [fileGroups]);

  async function saveVendor(file, vendorId) {
    await apiPatch(`/api/procurement/projects/${projectId}/files/${file.id}/vendor`, {
      vendorId,
      docRole: file.docRole || "",
    });
    setEditingId("");
    setChanged((n) => n + 1);
    await load();
  }

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
      </div>

      {changed > 0 ? (
        <div className="documents-rebuild-hint">
          Vendor changed. Rebuild the knowledge base from the Workspace tab so the
          comparison picks it up.
        </div>
      ) : null}

      <div className="file-search">
        <span aria-hidden="true">⌕</span>
        <input type="text" placeholder="Search files..." />
      </div>

      {fileGroups.map((group) => (
        <div key={group.title} className="file-group">
          <h3>{group.title}</h3>
          <div className="file-list">
            {group.files.map((file) => (
              <FileRow
                key={file.id || file.name}
                file={file}
                options={vendorOptions}
                editing={editingId === file.id}
                onEdit={() => setEditingId(file.id)}
                onCancel={() => setEditingId("")}
                onSave={(vendorId) => saveVendor(file, vendorId)}
              />
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}

export default DocumentsTab;
