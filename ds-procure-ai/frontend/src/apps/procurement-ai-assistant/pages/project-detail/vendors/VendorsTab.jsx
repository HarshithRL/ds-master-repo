import { useState } from "react";
import KbStatusBanner from "../KbStatusBanner";
import { useProjectView } from "../useProjectView";
import { apiPatch, apiPost } from "../../../../../services/api";
import "./vendors-tab.css";

function VendorsTab({ projectId }) {
  const { data, error } = useProjectView(projectId, "/vendors");
  const [picked, setPicked] = useState({});
  const [busyBid, setBusyBid] = useState("");
  const [noteDraft, setNoteDraft] = useState({});
  const [noteKind, setNoteKind] = useState({});
  const [savingNote, setSavingNote] = useState("");

  async function addVendorNote(bidId) {
    const text = (noteDraft[bidId] || "").trim();
    if (!text) return;
    setSavingNote(bidId);
    try {
      await apiPost(`/api/procurement/projects/${projectId}/notes`, {
        body: text,
        bid_id: bidId,
        kind: noteKind[bidId] || "note",
      });
      setNoteDraft((prev) => ({ ...prev, [bidId]: "" }));
      setNoteKind((prev) => ({ ...prev, [bidId]: "note" }));
    } catch (err) {
      window.alert(err?.message || "Could not save note.");
    } finally {
      setSavingNote("");
    }
  }

  async function toggleShortlist(bidId, next) {
    setBusyBid(bidId);
    setPicked((prev) => ({ ...prev, [bidId]: next }));
    try {
      await apiPatch(`/api/procurement/projects/${projectId}/vendors/${bidId}`, {
        shortlisted: next,
      });
    } catch (err) {
      setPicked((prev) => ({ ...prev, [bidId]: !next }));
      window.alert(err?.message || "Could not update selection.");
    } finally {
      setBusyBid("");
    }
  }

  if (!data && !error) {
    return <section className="vendors-tab">Loading…</section>;
  }

  if (error || !data) {
    return <section className="vendors-tab">{error ?? "Vendors unavailable."}</section>;
  }

  const vendors = data.vendors || [];
  const empty = vendors.length === 0;
  const emptyHint = empty
    ? data.kb_status === "ready" || data.kb_status === "needs_review"
      ? "No vendor bids extracted."
      : "Upload files to extract vendor bids."
    : null;

  return (
    <section className="vendors-tab">
      <div className="section-header">
        <div>
          <span className="section-eyebrow">VENDORS</span>
          <h2>Vendor shortlist</h2>
          <p>Bids classified from uploaded files, with coverage and BAFO facts from extraction.</p>
        </div>
        <span className="vendor-total">{data.total || 0} bids</span>
      </div>

      <KbStatusBanner
        kbStatus={data.kb_status}
        kbMessage={data.kb_message}
        emptyHint={emptyHint}
      />

      <div className="vendor-grid">
        {vendors.map((vendor) => (
          <article key={vendor.bid_id} className="vendor-card">
            <div className="vendor-card-head">
              <div>
                <label className="vendor-select">
                  <input
                    type="checkbox"
                    checked={picked[vendor.bid_id] ?? Boolean(vendor.shortlisted)}
                    disabled={busyBid === vendor.bid_id}
                    onChange={(event) =>
                      toggleShortlist(vendor.bid_id, event.target.checked)
                    }
                  />
                  <h3>{vendor.name}</h3>
                </label>
                <span>{vendor.legal_name}</span>
              </div>
              <em className={vendor.responded ? "responded" : "invited"}>
                {vendor.responded ? "Responded" : "Invited"}
              </em>
            </div>
            <p className="vendor-headline">{vendor.headline || "No commercial headline yet."}</p>
            <dl className="vendor-facts">
              <div>
                <dt>Coverage</dt>
                <dd>{vendor.coverage_pct || 0}%</dd>
              </div>
              <div>
                <dt>TCO</dt>
                <dd>{vendor.tco || "—"}</dd>
              </div>
              <div>
                <dt>Timeline</dt>
                <dd>{vendor.timeline || "—"}</dd>
              </div>
              <div>
                <dt>EcoVadis</dt>
                <dd>{vendor.ecovadis || "—"}</dd>
              </div>
              <div>
                <dt>Delivery</dt>
                <dd>{vendor.delivery_model || "—"}</dd>
              </div>
              <div>
                <dt>Files</dt>
                <dd>{vendor.file_count || 0}</dd>
              </div>
            </dl>
            {(vendor.files || []).length > 0 ? (
              <ul className="vendor-files">
                {vendor.files.map((name) => (
                  <li key={name}>{name}</li>
                ))}
              </ul>
            ) : null}

            <div className="vendor-note">
              <textarea
                rows={2}
                value={noteDraft[vendor.bid_id] || ""}
                placeholder={
                  (noteKind[vendor.bid_id] || "note") === "vendor_statement"
                    ? `Paste what ${vendor.name} sent — clarification email, call minutes`
                    : `Note on ${vendor.name} — e.g. reference call, risk, why shortlisted`
                }
                onChange={(event) =>
                  setNoteDraft((prev) => ({
                    ...prev,
                    [vendor.bid_id]: event.target.value,
                  }))
                }
              />
              <select
                className="vendor-note-kind"
                value={noteKind[vendor.bid_id] || "note"}
                aria-label="Who said this"
                onChange={(event) =>
                  setNoteKind((prev) => ({
                    ...prev,
                    [vendor.bid_id]: event.target.value,
                  }))
                }
              >
                <option value="note">Our note</option>
                <option value="vendor_statement">{vendor.name} said this</option>
              </select>
              <button
                type="button"
                className="vendor-note-btn"
                disabled={
                  savingNote === vendor.bid_id || !(noteDraft[vendor.bid_id] || "").trim()
                }
                onClick={() => addVendorNote(vendor.bid_id)}
              >
                {savingNote === vendor.bid_id ? "Saving…" : "Add note"}
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

export default VendorsTab;
