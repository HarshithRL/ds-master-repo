import { Routes, Route, Navigate } from "react-router-dom";

import Dashboard from "./pages/dashboard/dashboard";
import Projects from "./pages/projects/projects";
import ProjectDetail from "./pages/project-detail/ProjectDetail";
import { PROJECTS_LIST_PATH } from "./pages/new-project/paths";

function AppRoutes() {
  return (
    <Routes>

      {/* Default */}
      <Route
        path="/"
        element={
          <Navigate
            to="/app/procurement-ai-assistant/dashboard"
            replace
          />
        }
      />

      {/* Dashboard */}
      <Route
        path="/dashboard"
        element={<Dashboard />}
      />

      {/* Projects */}
      <Route
        path="/projects"
        element={<Projects />}
      />

      <Route
        path="/projects/new"
        element={<Navigate to={PROJECTS_LIST_PATH} replace />}
      />

      <Route
        path="/projects/new/chat"
        element={<Navigate to={PROJECTS_LIST_PATH} replace />}
      />

      <Route
        path="/projects/new/form"
        element={<Navigate to={PROJECTS_LIST_PATH} replace />}
      />

      {/* Project detail */}
      <Route
        path="/projects/:projectId"
        element={<ProjectDetail />}
      />

    </Routes>
  );
}

export default AppRoutes;
