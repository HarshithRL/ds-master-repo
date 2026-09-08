import { BrowserRouter, Routes, Route } from "react-router-dom";

import { ThemeProvider } from "./components/theme/ThemeProvider";
import { TooltipProvider } from "./components/ui/tooltip";
import Hub from "./pages/hub/Hub";
import ProcurementApp from "./apps/procurement-ai-assistant/App";

import "./App.css";

function App() {
  return (
    <ThemeProvider>
      <TooltipProvider>
      <BrowserRouter>
        <Routes>
          {/* Platform Hub */}
          <Route path="/" element={<Hub />} />

          {/* Procurement AI Assistant */}
          <Route
            path="/app/procurement-ai-assistant/*"
            element={<ProcurementApp />}
          />
        </Routes>
      </BrowserRouter>
      </TooltipProvider>
    </ThemeProvider>
  );
}

export default App;
