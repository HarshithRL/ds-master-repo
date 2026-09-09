import KbStatusBanner from "../KbStatusBanner";
import { useProjectView } from "../useProjectView";
import "./requirements-tab.css";

function RequirementsTab({ projectId }) {
  const { data, error } = useProjectView(projectId, "/requirements");

  if (!data && !error) {
    return <section className="requirements-tab">Loading…</section>;
  }

  if (error || !data) {
    return (
      <section className="requirements-tab">
        {error ?? "Requirements unavailable."}
      </section>
    );
  }

  const groups = data.groups || [];
  const empty = groups.length === 0;

  return (
    <section className="requirements-tab">
      <div className="section-header">
        <div>
          <span className="section-eyebrow">REQUIREMENTS</span>
          <h2>Procurement Requirements</h2>
          <p>R01–R40 seeded from the project overlay, with coverage from extracted evidence.</p>
        </div>
        <span className="req-total">{data.total || 0} items</span>
      </div>

      <KbStatusBanner
        kbStatus={data.kb_status}
        kbMessage={data.kb_message}
        emptyHint={empty ? "Upload files to extract requirements." : null}
      />

      {groups.map((group) => (
        <div key={group.category} className="req-group">
          <h3>{group.category}</h3>
          <div className="req-list">
            {(group.items || []).map((item) => (
              <div key={item.id} className="req-row">
                <div className="req-id">
                  <strong>{item.id}</strong>
                  {item.mandatory ? <em>Mandatory</em> : <em>Optional</em>}
                </div>
                <div className="req-body">
                  <p>{item.text}</p>
                  {item.section ? <span>{item.section}</span> : null}
                </div>
                <span className={`coverage-chip ${item.coverage || "gap"}`}>
                  {item.coverage || "gap"}
                </span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}

export default RequirementsTab;
