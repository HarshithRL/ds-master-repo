import { useEffect, useState } from "react";
import { apiGet } from "../../../../services/api";
import CreateProjectDialog from "../new-project/CreateProjectDialog";
import "./dashboard.css";

function Dashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    apiGet("/api/procurement/dashboard")
      .then(setData)
      .catch(() => setError("Unable to load dashboard."));
  }, []);

  if (!data && !error) {
    return (
      <div className="dashboard-page">
        <div className="dashboard-container">Loading…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dashboard-page">
        <div className="dashboard-container">{error}</div>
      </div>
    );
  }

  const { kpis, projectStatus, spendByCategory, topVendors, recentActivity } =
    data;

  return (
    <div className="dashboard-page">
      <div className="dashboard-container">

        <header className="dashboard-header">
          <div>
            <span className="dashboard-eyebrow">
              PROCUREMENT
            </span>

            <h1>Procurement Dashboard</h1>

            <p>
              Overview of procurement operations, projects, vendors and
              performance.
            </p>
          </div>

          <CreateProjectDialog />
        </header>

        <section className="dashboard-kpis">
          {kpis.map((kpi) => (
            <div key={kpi.label} className="kpi-card">
              <span className="kpi-label">{kpi.label}</span>
              <strong>{kpi.value}</strong>
              <span
                className={`kpi-change${kpi.positive ? " positive" : ""}`}
              >
                {kpi.change}
              </span>
            </div>
          ))}
        </section>

        <section className="dashboard-grid">

          <div className="dashboard-card project-status-card">
            <div className="card-header">
              <h2>Project Status</h2>
              <span>All Projects</span>
            </div>

            <div className="project-status">
              <div className="status-chart">
                <div className="status-circle">
                  <div className="status-circle-inner">
                    <strong>{projectStatus.total}</strong>
                    <span>Projects</span>
                  </div>
                </div>
              </div>

              <div className="status-list">
                {projectStatus.items.map((item) => (
                  <div key={item.label} className="status-item">
                    <span className={`status-dot ${item.dot}`} />
                    <span>{item.label}</span>
                    <strong>{item.count}</strong>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="dashboard-card">
            <div className="card-header">
              <h2>Spend by Category</h2>
              <span>This Month ▾</span>
            </div>

            <div className="spend-list">
              {spendByCategory.map((row) => (
                <div key={row.category} className="spend-row">
                  <span>{row.category}</span>
                  <div className="spend-bar">
                    <div style={{ width: `${row.barWidth}%` }} />
                  </div>
                  <strong>{row.amount}</strong>
                </div>
              ))}
            </div>
          </div>

          <div className="dashboard-card">
            <div className="card-header">
              <h2>Top Vendors by Spend</h2>
              <span>This Month ▾</span>
            </div>

            <div className="vendor-list">
              {topVendors.map((vendor) => (
                <div key={vendor.rank} className="vendor-row">
                  <span className="vendor-rank">{vendor.rank}</span>
                  <span>{vendor.name}</span>
                  <strong>{vendor.amount}</strong>
                </div>
              ))}
            </div>
          </div>

          <div className="dashboard-card">
            <div className="card-header">
              <h2>Recent Activity</h2>
              <span>View all →</span>
            </div>

            <div className="activity-list">
              {recentActivity.map((item) => (
                <div key={item.title} className="activity-item">
                  <div className="activity-icon">{item.icon}</div>
                  <div>
                    <strong>{item.title}</strong>
                    <span>{item.subtitle}</span>
                  </div>
                  <small>{item.timeAgo}</small>
                </div>
              ))}
            </div>
          </div>

        </section>

      </div>
    </div>
  );
}

export default Dashboard;
