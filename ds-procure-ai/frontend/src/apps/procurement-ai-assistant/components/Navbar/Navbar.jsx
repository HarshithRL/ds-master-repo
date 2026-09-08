import { useCallback, useEffect, useState } from "react";
import { Link, NavLink } from "react-router-dom";

import ThemeToggle from "../../../../components/theme/ThemeToggle";
import { useTheme } from "../../../../components/theme/useTheme";
import { apiGet } from "../../../../services/api";
import etexLogoDark from "../../../../assets/brand/etex-logo-dark.png";
import etexLogoLight from "../../../../assets/brand/etex-logo-light.png";
import IdentityPopup from "./IdentityPopup";
import "./navbar.css";

function displayNameFrom(identity) {
  const user = identity?.user;
  return user?.display_name || user?.user_name || user?.email || "Loading…";
}

function subtitleFrom(identity) {
  if (!identity) {
    return "";
  }
  return identity.user?.email || identity.env || "";
}

function initialFrom(name) {
  const trimmed = (name || "").trim();
  if (!trimmed || trimmed === "Loading…") {
    return "…";
  }
  return trimmed.charAt(0).toUpperCase();
}

function Navbar() {
  const { resolvedTheme } = useTheme();
  const brandLogo =
    resolvedTheme === "light" ? etexLogoLight : etexLogoDark;

  const [identity, setIdentity] = useState(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    apiGet("/api/auth")
      .then((data) => setIdentity(data))
      .catch(() => {
        setIdentity({
          env: "unknown",
          user: { display_name: "—", email: "Identity unavailable" },
          app: {},
        });
      });
  }, []);

  const closePopup = useCallback(() => setOpen(false), []);
  const togglePopup = useCallback(() => setOpen((current) => !current), []);

  const name = displayNameFrom(identity);
  const subtitle = subtitleFrom(identity);

  return (
    <>
      <aside className="navbar">

        <div className="navbar-brand">
          <Link
            to="/app/procurement-ai-assistant/dashboard"
            className="navbar-brand-link"
          >
            <img
              src={brandLogo}
              alt="Etex"
              className="navbar-logo"
            />

            <span className="navbar-mate">
              Nexus
            </span>
          </Link>
        </div>

        <div className="navbar-search">
          <span className="navbar-search-icon">
            ⌕
          </span>

          <input
            type="text"
            placeholder="Search"
            aria-label="Search"
          />

          <span className="navbar-search-shortcut">
            /
          </span>
        </div>

        <div className="navbar-section">

          <span className="navbar-section-title">
            WORKSPACE
          </span>

          <NavLink
            to="/app/procurement-ai-assistant/dashboard"
            className={({ isActive }) =>
              `navbar-link ${isActive ? "active" : ""}`
            }
          >
            <span className="navbar-link-icon">
              ✦
            </span>

            <span>
              Dashboard
            </span>
          </NavLink>

          <NavLink
            to="/app/procurement-ai-assistant/projects"
            className={({ isActive }) =>
              `navbar-link ${isActive ? "active" : ""}`
            }
          >
            <span className="navbar-link-icon">
              ◇
            </span>

            <span>
              Projects
            </span>
          </NavLink>

        </div>

        <div className="navbar-section navbar-secondary">

          <span className="navbar-section-title">
            SYSTEM
          </span>

          <ThemeToggle className="theme-toggle--navbar" />

          <NavLink
            to="/app/settings"
            className={({ isActive }) =>
              `navbar-link ${isActive ? "active" : ""}`
            }
          >
            <span className="navbar-link-icon">
              ⚙
            </span>

            <span>
              Settings
            </span>
          </NavLink>

          <NavLink
            to="/app/help"
            className={({ isActive }) =>
              `navbar-link ${isActive ? "active" : ""}`
            }
          >
            <span className="navbar-link-icon">
              ?
            </span>

            <span>
              Help
            </span>
          </NavLink>

        </div>

        <div className="navbar-user">
          <button
            type="button"
            className="navbar-user-trigger"
            onClick={togglePopup}
            aria-expanded={open}
            aria-haspopup="dialog"
          >
            <div className="navbar-avatar">
              {initialFrom(name)}
            </div>

            <div className="navbar-user-info">
              <span className="navbar-user-name">
                {name}
              </span>
              <span className="navbar-user-role">
                {subtitle}
              </span>
            </div>
          </button>

          <button
            className="navbar-user-menu"
            type="button"
            aria-label="User identity"
            aria-expanded={open}
            onClick={togglePopup}
          >
            •••
          </button>
        </div>

      </aside>

      {open ? (
        <IdentityPopup identity={identity} onClose={closePopup} />
      ) : null}
    </>
  );
}

export default Navbar;
