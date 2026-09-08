import KbStatusBanner from "../KbStatusBanner";
import { useProjectView } from "../useProjectView";
import "./vendors-tab.css";

function VendorsTab({ projectId }) {
  const { data, error } = useProjectView(projectId, "/vendors");

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
                <h3>{vendor.name}</h3>
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
          </article>
        ))}
      </div>
    </section>
  );
}

export default VendorsTab;
