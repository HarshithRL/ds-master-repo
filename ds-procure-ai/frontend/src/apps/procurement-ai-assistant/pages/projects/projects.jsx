import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiGet } from "../../../../services/api";
import CreateProjectDialog from "../new-project/CreateProjectDialog";
import "./projects.css";

function Projects() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    apiGet("/api/procurement/projects")
      .then(setData)
      .catch(() => setError("Unable to load projects."));
  }, []);

  const openProject = (project) => {
    navigate(
      `/app/procurement-ai-assistant/projects/${project.id}`
    );
  };

  if (!data && !error) {
    return (
      <div className="projects-page">
        <div className="projects-container">Loading…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="projects-page">
        <div className="projects-container">{error}</div>
      </div>
    );
  }

  const { summary, filters, pagination, projects } = data;

  return (
    <div className="projects-page">
      <div className="projects-container">

        <header className="projects-header">
          <div>
            <span className="projects-eyebrow">
              PROCUREMENT
            </span>

            <h1>Projects</h1>

            <p>
              Manage procurement projects, workflows and
              project activity.
            </p>
          </div>

          <CreateProjectDialog />
        </header>

        <section className="project-summary-grid">
          {summary.map((card) => (
            <div key={card.label} className="summary-card">
              <span>{card.label}</span>
              <strong>{card.value}</strong>
              <small>{card.trend}</small>
            </div>
          ))}
        </section>

        <section className="projects-content">

          <div className="projects-toolbar">

            <input
              type="text"
              placeholder="Search projects..."
            />

            <select defaultValue="all">
              {filters.status.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>

            <select defaultValue="all">
              {filters.category.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>

            <button className="reset-button" type="button">
              ↻ Reset
            </button>

          </div>

          <div className="projects-table">

            <div className="project-row project-row-header">
              <span>Project</span>
              <span>Category</span>
              <span>Owner</span>
              <span>Status</span>
              <span>Priority</span>
              <span>Budget</span>
              <span>Progress</span>
            </div>

            {projects.map((project) => (
              <button
                key={project.id}
                type="button"
                className="project-row project-row-clickable"
                onClick={() => openProject(project)}
              >

                <span className="project-name-cell">
                  <strong>{project.name}</strong>
                  <small>{project.projectId}</small>
                </span>

                <span>{project.category}</span>
                <span>{project.owner}</span>

                <span>
                  <span
                    className={`status-dot ${project.status
                      .toLowerCase()
                      .replaceAll(" ", "-")}`}
                  />
                  {project.status}
                </span>

                <span>
                  <span
                    className={`priority-badge ${project.priority.toLowerCase()}`}
                  >
                    {project.priority}
                  </span>
                </span>

                <span>{project.budget}</span>

                <span className="progress-cell">
                  <span>{project.progress}%</span>
                  <span className="progress-bar">
                    <span
                      style={{
                        width: `${project.progress}%`,
                      }}
                    />
                  </span>
                </span>

              </button>
            ))}

          </div>

          <div className="projects-footer">
            Showing {pagination.from} to {pagination.to} of{" "}
            {pagination.total} projects

            <div className="pagination">
              <button type="button">‹</button>
              {pagination.pages.map((page) => (
                <button
                  key={page}
                  type="button"
                  className={
                    page === pagination.currentPage ? "active" : ""
                  }
                >
                  {page}
                </button>
              ))}
              <button type="button">›</button>
            </div>
          </div>

        </section>

      </div>
    </div>
  );
}

export default Projects;
