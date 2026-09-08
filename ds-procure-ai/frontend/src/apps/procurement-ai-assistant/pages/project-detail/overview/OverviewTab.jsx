import KbStatusBanner from "../KbStatusBanner";
import { useProjectView } from "../useProjectView";
import "./overview-tab.css";

function ProgressRing({ value }) {
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (value / 100) * circumference;

  return (
    <div className="progress-ring" aria-label={`${value}% complete`}>
      <svg viewBox="0 0 140 140" width="140" height="140">
        <circle className="progress-ring-track" cx="70" cy="70" r={radius} />
        <circle
          className="progress-ring-value"
          cx="70"
          cy="70"
          r={radius}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>
      <div className="progress-ring-label">
        <strong>{value}%</strong>
        <span>Complete</span>
      </div>
    </div>
  );
}

function OverviewTab({ projectId }) {
  const { data, error } = useProjectView(projectId, "/overview");

  if (!data && !error) {
    return <div className="overview-tab">Loading…</div>;
  }

  if (error || !data) {
    return <div className="overview-tab">{error ?? "Overview unavailable."}</div>;
  }

  const project = data.project || {};
  const stages = data.stages || [];
  const metrics = data.metrics || [];
  const milestones = data.milestones || [];
  const insights = data.insights || [];
  const approvals = data.approvals || [];
  const quickActions = data.quickActions || [];
  const documents = data.documents || { pdf: 0, docx: 0, xlsx: 0, recent: [] };
  const requirements = data.requirements || { total: 0, approved: 0, pending: 0, rejected: 0 };
  const vendors = data.vendors || { invited: 0, responded: 0, shortlisted: 0 };
  const noFiles = (documents.pdf || 0) + (documents.docx || 0) + (documents.xlsx || 0) === 0
    && !(documents.recent || []).length;

  return (
    <div className="overview-tab">
      <KbStatusBanner
        kbStatus={data.kb_status}
        kbMessage={data.kb_message}
        emptyHint={noFiles ? "Upload files to extract project knowledge." : null}
      />
      <div className="overview-grid">
        <section className="overview-card overview-card-progress">
          <div className="overview-card-head">
            <h2>Project Progress</h2>
            <span>{project.code}</span>
          </div>
          <div className="progress-body">
            <ProgressRing value={project.progress || 0} />
            <ul className="progress-stages">
              {stages.map((stage) => (
                <li
                  key={stage.name}
                  className={
                    stage.done
                      ? "done"
                      : stage.current
                        ? "current"
                        : ""
                  }
                >
                  <span className="stage-dot" />
                  {stage.name}
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="overview-card overview-card-metrics">
          <div className="overview-card-head">
            <h2>Key Metrics</h2>
          </div>
          <div className="metrics-grid">
            {metrics.map((metric) => (
              <div key={metric.label} className="metric-tile">
                <span>{metric.label}</span>
                <strong>{metric.value}</strong>
              </div>
            ))}
          </div>
        </section>

        <section className="overview-card">
          <div className="overview-card-head">
            <h2>Upcoming Milestones</h2>
          </div>
          <ul className="milestone-list">
            {milestones.length === 0 ? (
              <li className="empty-row">No milestones extracted yet.</li>
            ) : null}
            {milestones.map((item) => (
              <li key={item.title}>
                <div>
                  <strong>{item.title}</strong>
                  <span>{item.date}</span>
                </div>
                <em className={`milestone-status ${(item.status || "upcoming").toLowerCase().replace(/\s+/g, "-")}`}>
                  {item.status}
                </em>
              </li>
            ))}
          </ul>
        </section>

        <section className="overview-card">
          <div className="overview-card-head">
            <h2>AI Insights</h2>
          </div>
          <ul className="insight-list">
            {insights.length === 0 ? (
              <li className="empty-row">No AI insights yet.</li>
            ) : null}
            {insights.map((insight) => (
              <li key={insight.title} className={`insight-${insight.type}`}>
                <strong>{insight.title}</strong>
                <p>{insight.body}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="overview-card">
          <div className="overview-card-head">
            <h2>Requirements</h2>
          </div>
          <div className="stat-row">
            <div>
              <span>Total</span>
              <strong>{requirements.total}</strong>
            </div>
            <div>
              <span>Approved</span>
              <strong>{requirements.approved}</strong>
            </div>
            <div>
              <span>Pending</span>
              <strong>{requirements.pending}</strong>
            </div>
            <div>
              <span>Rejected</span>
              <strong>{requirements.rejected}</strong>
            </div>
          </div>
        </section>

        <section className="overview-card">
          <div className="overview-card-head">
            <h2>Vendors</h2>
          </div>
          <div className="stat-row">
            <div>
              <span>Invited</span>
              <strong>{vendors.invited}</strong>
            </div>
            <div>
              <span>Responded</span>
              <strong>{vendors.responded}</strong>
            </div>
            <div>
              <span>Shortlisted</span>
              <strong>{vendors.shortlisted}</strong>
            </div>
          </div>
        </section>

        <section className="overview-card">
          <div className="overview-card-head">
            <h2>Documents & Artifacts</h2>
          </div>
          <div className="doc-type-row">
            <span className="doc-chip pdf">PDF {documents.pdf || 0}</span>
            <span className="doc-chip docx">DOCX {documents.docx || 0}</span>
            <span className="doc-chip xlsx">XLSX {documents.xlsx || 0}</span>
          </div>
          <ul className="recent-docs">
            {(documents.recent || []).map((name) => (
              <li key={name}>{name}</li>
            ))}
          </ul>
        </section>

        <section className="overview-card">
          <div className="overview-card-head">
            <h2>Tasks & Approvals</h2>
          </div>
          <ul className="approval-list">
            {approvals.map((item) => (
              <li key={item.title}>
                <div>
                  <strong>{item.title}</strong>
                  <span>{item.owner}</span>
                </div>
                <em className={`approval-status ${item.status.toLowerCase()}`}>
                  {item.status}
                </em>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className="overview-quick-actions">
        <div className="overview-card-head">
          <h2>Quick Actions</h2>
        </div>
        <div className="quick-action-row">
            {quickActions.map((action) => (
            <button key={action} type="button" className="quick-action-btn">
              {action}
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}

export default OverviewTab;
