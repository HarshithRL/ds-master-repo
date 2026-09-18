import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { apiGet, apiPatch, apiDelete } from "../../../../services/api";
import OverviewTab from "./overview/OverviewTab";
import WorkspaceTab from "./workspace/WorkspaceTab";
import DocumentsTab from "./documents/DocumentsTab";
import RequirementsTab from "./requirements/RequirementsTab";
import VendorsTab from "./vendors/VendorsTab";
import "./project-detail.css";

function ProjectDetail() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabFromUrl = searchParams.get("tab") || "overview";
  const [activeTab, setActiveTab] = useState(tabFromUrl);
  const [shell, setShell] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState("");
  const loadedRef = useRef(false);

  useEffect(() => {
    setActiveTab(tabFromUrl);
  }, [tabFromUrl]);

  const refreshShell = useCallback(() => {
    if (!projectId) {
      return;
    }
    apiGet(`/api/procurement/projects/${projectId}`)
      .then((payload) => {
        loadedRef.current = true;
        setError(null);
        setShell(payload);
      })
      .catch(() => {
        if (!loadedRef.current) {
          setError("Unable to load project.");
        }
      });
  }, [projectId]);

  useEffect(() => {
    loadedRef.current = false;
    setShell(null);
    setError(null);
    refreshShell();
  }, [projectId, refreshShell]);

  function selectTab(tabId) {
    setActiveTab(tabId);
    if (tabId === "overview") {
      setSearchParams({}, { replace: true });
      return;
    }
    setSearchParams({ tab: tabId }, { replace: true });
  }

  async function handleRename(currentName) {
    const next = window.prompt("Rename project", currentName || "");
    if (next === null) {
      return;
    }
    const name = next.trim();
    if (!name || name === currentName) {
      return;
    }
    setBusy("rename");
    try {
      await apiPatch(`/api/procurement/projects/${projectId}`, { name });
      refreshShell();
    } catch (err) {
      window.alert(err?.message || "Rename failed.");
    } finally {
      setBusy("");
    }
  }

  async function handleDelete(currentName) {
    const ok = window.confirm(
      `Delete "${currentName}"? This permanently removes the project, its files and all extracted data.`,
    );
    if (!ok) {
      return;
    }
    setBusy("delete");
    try {
      await apiDelete(`/api/procurement/projects/${projectId}`);
      navigate("/app/procurement-ai-assistant/projects", { replace: true });
    } catch (err) {
      window.alert(err?.message || "Delete failed.");
      setBusy("");
    }
  }

  if (!shell && !error) {
    return (
      <div className="project-detail-page">
        <div className="project-detail-container">Loading…</div>
      </div>
    );
  }

  if (error || !shell) {
    return (
      <div className="project-detail-page">
        <div className="project-detail-container">
          {error ?? "Project not found."}
        </div>
      </div>
    );
  }

  const { project, tabs } = shell;

  return (
    <div
      className={`project-detail-page${activeTab === "workspace" ? " is-workspace" : ""}`}
    >
      <div
        className={`project-detail-container${activeTab === "workspace" ? " is-workspace" : ""}`}
      >
        <div className="project-breadcrumb">
          <Link to="/app/procurement-ai-assistant/projects">Projects</Link>
          <span>›</span>
          <strong>{project.name}</strong>
        </div>

        <header className="project-detail-header">
          <div>
            <span className="project-detail-eyebrow">
              PROCUREMENT PROJECT
            </span>

            <h1>{project.name}</h1>

            <div className="project-meta">
              <span className="project-status-badge">{project.status}</span>
              <span>{project.code}</span>
              <span>•</span>
              <span>Owner: {project.owner}</span>
              <span>•</span>
              <span>Created {project.created}</span>
              <span>•</span>
              <span>Deadline {project.deadline}</span>
            </div>
          </div>

          <div className="project-header-actions">
            <button
              type="button"
              className="secondary-button"
              disabled={busy !== ""}
              onClick={() => handleRename(project.name)}
            >
              {busy === "rename" ? "Renaming…" : "Rename"}
            </button>
            <button
              type="button"
              className="secondary-button is-danger"
              disabled={busy !== ""}
              onClick={() => handleDelete(project.name)}
            >
              {busy === "delete" ? "Deleting…" : "Delete"}
            </button>
          </div>
        </header>

        <nav className="project-tabs" aria-label="Project sections">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`project-tab${activeTab === tab.id ? " active" : ""}`}
              onClick={() => selectTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        <div className="project-tab-body">
          {activeTab === "overview" && (
            <OverviewTab projectId={projectId} />
          )}
          {activeTab === "workspace" && (
            <WorkspaceTab
              projectId={projectId}
              onProjectUpdated={refreshShell}
            />
          )}
          {activeTab === "documents" && (
            <DocumentsTab projectId={projectId} />
          )}
          {activeTab === "requirements" && (
            <RequirementsTab projectId={projectId} />
          )}
          {activeTab === "vendors" && (
            <VendorsTab projectId={projectId} />
          )}
          {activeTab === "activity" && (
            <section className="project-tab-placeholder">
              <p>Recent project activity will appear here.</p>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

export default ProjectDetail;
