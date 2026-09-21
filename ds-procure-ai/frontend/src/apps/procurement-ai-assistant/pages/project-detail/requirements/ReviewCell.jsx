import { useState } from "react";

import { apiDelete, apiPatch } from "../../../../../services/api";

const STATUSES = ["met", "partial", "not_offered", "not_stated", "unclear"];

function ReviewCell({ projectId, requirementId, bid, onSaved }) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState(bid.status || "not_stated");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const base = `/api/procurement/projects/${projectId}/requirements/${requirementId}/vendors/${bid.bid_id}`;

  async function run(action) {
    setBusy(true);
    setError(null);
    try {
      await action();
      setOpen(false);
      setNote("");
      onSaved?.();
    } catch (err) {
      setError(err?.message || "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="req-cell">
      <button
        type="button"
        className={`req-status is-${bid.status || "not_stated"}${bid.reviewed ? " is-reviewed" : ""}`}
        onClick={() => setOpen((v) => !v)}
        title={bid.reviewed ? "Reviewed by a human — click to change" : "Click to override"}
      >
        <span className="req-cell-vendor" title={bid.label}>
          {bid.label}
        </span>
        <span className="req-cell-value">
          {bid.status || "not_stated"}
          {bid.reviewed ? " ✓" : ""}
        </span>
      </button>

      {open ? (
        <div className="req-review">
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <textarea
            rows={2}
            value={note}
            placeholder="Why? e.g. confirmed on the BAFO call 18/09, minutes filed"
            onChange={(e) => setNote(e.target.value)}
          />
          {error ? <p className="req-review-error">{error}</p> : null}
          <div className="req-review-actions">
            <button
              type="button"
              className="req-review-save"
              disabled={busy}
              onClick={() => run(() => apiPatch(base, { status, note }))}
            >
              {busy ? "Saving…" : "Save override"}
            </button>
            {bid.reviewed ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => run(() => apiDelete(base))}
                title="Hand this cell back to the model"
              >
                Clear
              </button>
            ) : null}
            <button type="button" disabled={busy} onClick={() => setOpen(false)}>
              Cancel
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default ReviewCell;
