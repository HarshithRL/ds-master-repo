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
          <div className="req-evidence">
            {bid.analyst_note ? (
              <div className="req-evidence-block is-analyst">
                <span className="req-evidence-label">Analyst</span>
                <blockquote className="req-evidence-quote">{bid.analyst_note}</blockquote>
              </div>
            ) : null}

            {bid.claim ? (
              <div className="req-evidence-block">
                {bid.analyst_note ? (
                  <span className="req-evidence-label">Model evidence it replaced</span>
                ) : null}
                <blockquote className="req-evidence-quote">{bid.claim}</blockquote>
              </div>
            ) : bid.analyst_note ? null : (
              <p className="req-evidence-empty">
                {bid.status === "not_stated"
                  ? "No passage in this bid addresses the requirement."
                  : "No quote was recorded for this verdict."}
              </p>
            )}

            <p className="req-evidence-meta">
              {bid.citation ? <span>{bid.citation}</span> : null}
              {bid.page != null ? <span>p.{bid.page}</span> : null}
              {typeof bid.confidence === "number" ? (
                <span>confidence {bid.confidence.toFixed(2)}</span>
              ) : null}
              {bid.reviewed ? <span className="is-reviewed">human reviewed</span> : null}
            </p>
            {bid.warning ? <p className="req-evidence-warning">{bid.warning}</p> : null}
          </div>

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
