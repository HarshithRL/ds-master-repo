import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Spinner } from "@/components/ui/spinner";
import { apiGet } from "../../../../services/api";
import CreateProjectDialog from "../new-project/CreateProjectDialog";
import "./projects.css";

function Projects() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const anyBuilding = (data?.projects || []).some((p) => p.building);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      apiGet("/api/procurement/projects")
        .then((next) => {
          if (!cancelled) setData(next);
        })
        .catch(() => {
          if (!cancelled) setError("Unable to load projects.");
        });

    load();
    // Keep the spinner honest: only poll while something is actually running.
    const timer = anyBuilding ? window.setInterval(load, 10000) : null;
    return () => {
      cancelled = true;
      if (timer) window.clearInterval(timer);
    };
  }, [anyBuilding]);

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

  const { filters, pagination, projects } = data;

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
              <span>Creator</span>
              <span>Status</span>
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

                <span className="status-cell">
                  <span
                    className={`status-dot ${project.status
                      .toLowerCase()
                      .replaceAll(" ", "-")}`}
                  />
                  {project.status}
                </span>

                <span className="progress-cell">
                  <span className={`stage-chip is-${project.stage || "no_files"}`}>
                    {project.building ? <Spinner /> : <span className="stage-dot" />}
                    {project.stageLabel || "No files"}
                  </span>
                  {project.stage === "ready" || project.stage === "needs_review" ? (
                    <span className="stage-coverage">
                      <span>{project.progress}%</span>
                      <span className="progress-bar">
                        <span
                          style={{
                            width: `${project.progress}%`,
                          }}
                        />
                      </span>
                    </span>
                  ) : null}
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
