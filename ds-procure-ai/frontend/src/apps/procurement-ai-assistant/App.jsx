import Navbar from "./components/Navbar/Navbar";
import { useLocation } from "react-router-dom";

import AppRoutes from "./routes";

import "./app.css";

function ProcurementApp() {
  const location = useLocation();
  const isWorkspaceRoute =
    location.pathname.startsWith("/app/procurement-ai-assistant/projects/") &&
    new URLSearchParams(location.search).get("tab") === "workspace";

  return (
    <div className="procurement-app">

      <Navbar />

      <main className={`procurement-main${isWorkspaceRoute ? " is-workspace" : ""}`}>
        <AppRoutes />
      </main>

    </div>
  );
}

export default ProcurementApp;
