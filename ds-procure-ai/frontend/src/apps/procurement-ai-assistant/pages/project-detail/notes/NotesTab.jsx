import { useCallback, useEffect, useState } from "react";
import { apiGet, apiPost, apiDelete } from "../../../../../services/api";
import "./notes-tab.css";

const KINDS = [
  { value: "note", label: "Note" },
  { value: "risk", label: "Risk" },
  { value: "decision", label: "Decision" },
  { value: "question", label: "Question" },
];

function NotesTab({ projectId }) {
  const [notes, setNotes] = useState(null);
  const [error, setError] = useState(null);
  const [body, setBody] = useState("");
  const [kind, setKind] = useState("note");
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    if (!projectId) return;
    apiGet(`/api/procurement/projects/${projectId}/notes`)
      .then((payload) => {
        setNotes(payload.notes || []);
        setError(null);
      })
      .catch(() => setError("Unable to load notes."));
  }, [projectId]);

  useEffect(() => {
    setNotes(null);
    load();
  }, [load]);

  async function addNote(event) {
    event.preventDefault();
    const text = body.trim();
    if (!text) return;
    setSaving(true);
    try {
      await apiPost(`/api/procurement/projects/${projectId}/notes`, {
        body: text,
        kind,
      });
      setBody("");
      setKind("note");
      load();
    } catch (err) {
      window.alert(err?.message || "Could not save note.");
    } finally {
      setSaving(false);
    }
  }

  async function removeNote(noteId) {
    if (!window.confirm("Delete this note?")) return;
    try {
      await apiDelete(`/api/procurement/projects/${projectId}/notes/${noteId}`);
      load();
    } catch (err) {
      window.alert(err?.message || "Could not delete note.");
    }
  }

  return (
    <section className="notes-tab">
      <div className="section-header">
        <div>
          <span className="section-eyebrow">NOTES</span>
          <h2>Decision log</h2>
          <p>
            Judgment the documents cannot supply — reference calls, risks, and why
            a bid was chosen or rejected.
          </p>
        </div>
      </div>

      <form className="note-form" onSubmit={addNote}>
        <select value={kind} onChange={(event) => setKind(event.target.value)}>
          {KINDS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <textarea
          value={body}
          onChange={(event) => setBody(event.target.value)}
          placeholder="e.g. PwC confirmed on 18 Sep they cannot start before Q1 — timeline risk."
          rows={3}
        />
        <button type="submit" className="primary-button" disabled={saving || !body.trim()}>
          {saving ? "Saving…" : "Add note"}
        </button>
      </form>

      {error ? <p className="note-error">{error}</p> : null}

      {notes === null ? (
        <p className="note-empty">Loading…</p>
      ) : notes.length === 0 ? (
        <p className="note-empty">No notes yet.</p>
      ) : (
        <ul className="note-list">
          {notes.map((note) => (
            <li key={note.id} className={`note-item ${note.kind}`}>
              <div className="note-item-head">
                <span className={`note-kind ${note.kind}`}>{note.kind}</span>
                {note.bid_id ? <span className="note-bid">{note.bid_id}</span> : null}
                {note.source !== "manual" ? (
                  <span className="note-source">via {note.source}</span>
                ) : null}
                <small>{note.created_at}</small>
                <button
                  type="button"
                  className="note-delete"
                  onClick={() => removeNote(note.id)}
                  aria-label="Delete note"
                >
                  ×
                </button>
              </div>
              <p>{note.body}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default NotesTab;
