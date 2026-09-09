import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  BarChart3,
  Box,
  ChevronDown,
  ClipboardCheck,
  FileText,
  Factory,
  Globe2,
  LineChart,
  Network,
  Search,
  ShieldCheck,
  UsersRound,
  X,
} from "lucide-react";

import ThemeToggle from "../../components/theme/ThemeToggle";
import { useTheme } from "../../components/theme/useTheme";
import { apiGet } from "../../services/api";
import { createLogger } from "../../shared/logger-global/index.js";
import etexLogoDark from "../../assets/brand/etex-logo-dark.png";
import etexLogoLight from "../../assets/brand/etex-logo-light.png";

import "./hub.css";

const log = createLogger("pages.hub");

const HIDDEN_HUB_TOOL_IDS = new Set(["accounting", "policy-search"]);
const HIDDEN_HUB_TOOL_NAMES = new Set(["Accounting Assistant", "Policy Search"]);

const HUB_TOOL_DISPLAY_NAMES = {
  "document-builder": "Finance Agent",
  "document-translator": "Supply chain agent",
  "scope-builder": "Manufacturing agent",
};

const HUB_TOOL_DESCRIPTIONS = {
  "document-builder": "Plan, analyse and explain financial work",
  "document-translator": "Surface supply risks and coordinate responses",
  "scope-builder": "Turn operational signals into actions",
};

const FEATURED_TAGS = ["Projects", "Document analysis", "Vendor comparison"];

const PLATFORM_UPDATES = [
  {
    icon: "network",
    title: "New connectors for document sources and systems",
    meta: "Coming soon",
  },
  {
    icon: "shield",
    title: "Enhanced data governance and controls",
    meta: "Coming soon",
  },
  {
    icon: "line-chart",
    title: "Expanded analytics and insights",
    meta: "Coming soon",
  },
];

function brandNameForDisplay(name) {
  return name === "Mate" ? "Nexus" : name;
}

function displayNameFrom(identity) {
  const user = identity?.user;
  return user?.display_name || user?.user_name || user?.email || "";
}

function initialsFrom(identity) {
  const displayName = displayNameFrom(identity).trim();
  if (!displayName) {
    return "AB";
  }

  const parts = displayName.split(/\s+/).filter(Boolean);
  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase();
  }
  return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
}

function categoriesForDisplay(categories) {
  const visible = [];
  for (const category of categories ?? []) {
    const tools = [];
    for (const tool of category.tools ?? []) {
      if (
        HIDDEN_HUB_TOOL_IDS.has(tool.id) ||
        HIDDEN_HUB_TOOL_NAMES.has(tool.name)
      ) {
        continue;
      }
      tools.push({
        ...tool,
        name: HUB_TOOL_DISPLAY_NAMES[tool.id] ?? tool.name,
        description: HUB_TOOL_DESCRIPTIONS[tool.id] ?? tool.description,
      });
    }
    if (tools.length > 0) {
      visible.push({ ...category, tools });
    }
  }
  return visible;
}

function renderToolIcon(id, props) {
  switch (id) {
    case "procurement-ai-assistant":
      return <ClipboardCheck {...props} />;
    case "document-builder":
      return <BarChart3 {...props} />;
    case "document-translator":
      return <Globe2 {...props} />;
    case "scope-builder":
      return <Factory {...props} />;
    default:
      return <Box {...props} />;
  }
}

function ModuleIcon({ tool, featured = false }) {
  return (
    <div className={featured ? "hub-feature-icon" : "hub-module-icon"}>
      {renderToolIcon(tool?.id, { "aria-hidden": "true", strokeWidth: 1.7 })}
    </div>
  );
}

function renderUpdateIcon(id) {
  switch (id) {
    case "network":
      return <Network aria-hidden="true" size={30} strokeWidth={1.7} />;
    case "shield":
      return <ShieldCheck aria-hidden="true" size={30} strokeWidth={1.7} />;
    default:
      return <LineChart aria-hidden="true" size={30} strokeWidth={1.7} />;
  }
}

function NexusMap() {
  return (
    <div className="hub-nexus-map" aria-hidden="true">
      <div className="hub-nexus-core">
        <span />
      </div>
      <div className="hub-map-node hub-map-node--document">
        <FileText size={28} strokeWidth={1.5} />
      </div>
      <div className="hub-map-node hub-map-node--box">
        <Box size={28} strokeWidth={1.5} />
      </div>
      <div className="hub-map-node hub-map-node--chart">
        <BarChart3 size={30} strokeWidth={1.5} />
      </div>
      <div className="hub-map-node hub-map-node--users">
        <UsersRound size={30} strokeWidth={1.5} />
      </div>
      <svg className="hub-map-lines" viewBox="0 0 620 220" focusable="false">
        <path d="M250 92 C190 42 108 40 70 72 C33 103 48 132 100 132 L248 132" />
        <path d="M250 111 C205 160 145 164 98 164" />
        <path d="M372 90 C400 34 487 28 548 58" />
        <path d="M372 124 L548 124 C588 124 570 166 610 160" />
        <path d="M372 150 L478 150" />
        <circle cx="62" cy="72" r="5" />
        <circle cx="121" cy="132" r="4" />
        <circle cx="394" cy="48" r="5" />
        <circle cx="430" cy="150" r="4" />
        <circle cx="610" cy="154" r="5" />
      </svg>
    </div>
  );
}

function Hub() {
  const [page, setPage] = useState(null);
  const [error, setError] = useState(null);
  const [identity, setIdentity] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const { resolvedTheme } = useTheme();
  // Filenames are theme targets: *-light = dark ink, *-dark = white reverse
  const brandLogo =
    resolvedTheme === "light" ? etexLogoLight : etexLogoDark;

  useEffect(() => {
    apiGet("/api/auth")
      .then((data) => {
        setIdentity(data);
        return data;
      })
      .catch((err) => {
        log.warn("Failed to resolve identity", { context: { error: String(err) } });
      })
      .then(() => apiGet("/api/hub"))
      .then((data) => {
        log.debug("Hub API loaded", { context: { toolCount: data?.categories?.length } });
        setPage(data);
      })
      .catch((err) => {
        log.error("Failed to load Hub", { context: { error: String(err) } });
        setError("Unable to load Hub.");
      });
  }, []);

  // --------------------------------------------------
  // Loading
  // --------------------------------------------------

  if (!page && !error) {
    return (
      <div className="hub-loading">
        <span className="hub-loading-mark" />
        Loading Nexus...
      </div>
    );
  }

  // --------------------------------------------------
  // Error
  // --------------------------------------------------

  if (error) {
    return <div className="hub-loading">{error}</div>;
  }

  const categories = categoriesForDisplay(page.categories);
  const tools = categories.flatMap((category) => category.tools);
  const featuredTool =
    tools.find((tool) => tool.id === "procurement-ai-assistant") ??
    tools.find((tool) => tool.available !== false);
  const upcomingTools = tools.filter((tool) => tool.id !== featuredTool?.id);
  const heroDescription = "Your workspace for Etex AI modules";

  // --------------------------------------------------
  // Hub
  // --------------------------------------------------

  return (
    <div className="hub">
      <div className="hub-container">

        <header className="hub-header">
          <div className="hub-brand">

            <img
              src={brandLogo}
              alt="Etex"
              className="hub-etex-logo"
            />

            <span className="hub-brand-divider" />

            <span className="hub-mate-name">
              {brandNameForDisplay(page.brand.name)}
            </span>
          </div>

          <div className="hub-search">
            <Search aria-hidden="true" size={24} strokeWidth={1.7} />
            <input
              aria-label="Search Nexus"
              type="search"
              placeholder="Search Nexus"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
            {searchQuery ? (
              <button
                type="button"
                className="hub-search-clear"
                aria-label="Clear search"
                onClick={() => setSearchQuery("")}
              >
                <X aria-hidden="true" size={16} strokeWidth={2} />
              </button>
            ) : null}
          </div>

          <div className="hub-actions">
            <ThemeToggle className="hub-theme-toggle" />
            <span className="hub-action-divider" />
            <div className="hub-user-display" aria-label="Current user">
              <span>{initialsFrom(identity)}</span>
              <ChevronDown aria-hidden="true" size={18} strokeWidth={1.8} />
            </div>
          </div>
        </header>

        <section className="hub-hero" aria-labelledby="hub-title">

          <div className="welcome-content">

            <h1 id="hub-title">
              Welcome to Nexus
            </h1>

            <p>
              {heroDescription}
            </p>

          </div>

          <NexusMap />

        </section>

        {featuredTool ? (
          <section className="hub-featured" aria-labelledby="hub-featured-title">
            <ModuleIcon tool={featuredTool} featured />

            <div className="hub-featured-copy">
              <div className="hub-featured-heading">
                <h2 id="hub-featured-title">{featuredTool.name}</h2>
                <span>Available now</span>
              </div>
              <p>
                Compare vendor responses, organise project evidence, and reach
                decisions faster.
              </p>
              <div className="hub-tags" aria-label="Module capabilities">
                {FEATURED_TAGS.map((tag) => (
                  <span key={tag}>{tag}</span>
                ))}
              </div>
            </div>

            {featuredTool.available === false ? (
              <div className="hub-featured-disabled" aria-disabled="true">
                Coming soon
              </div>
            ) : (
              <Link className="hub-featured-cta" to={featuredTool.path}>
                Open Procurement
              </Link>
            )}
          </section>
        ) : null}

        {upcomingTools.length > 0 ? (
          <section className="hub-upcoming" aria-labelledby="hub-upcoming-title">
            <h2 id="hub-upcoming-title">Explore upcoming modules</h2>

            <div className="hub-module-grid">
              {upcomingTools.map((tool) => (
                <article
                  key={tool.id ?? tool.name}
                  className="hub-module-card"
                  aria-disabled={tool.available === false ? "true" : undefined}
                >
                  <ModuleIcon tool={tool} />
                  <div className="hub-module-copy">
                    <h3>{tool.name}</h3>
                    <p>{tool.description}</p>
                    <span className="hub-development-status">
                      <span aria-hidden="true" />
                      In development
                    </span>
                  </div>
                </article>
              ))}
            </div>
          </section>
        ) : null}

        <section className="hub-platform-updates" aria-labelledby="hub-updates-title">
          <h2 id="hub-updates-title">Platform updates</h2>

          <div className="hub-update-list">
            {PLATFORM_UPDATES.map((item) => {
              return (
                <article className="hub-update-item" key={item.title}>
                  <div className="hub-update-icon">
                    {renderUpdateIcon(item.icon)}
                  </div>
                  <div>
                    <h3>{item.title}</h3>
                    <p>{item.meta}</p>
                  </div>
                </article>
              );
            })}
          </div>
        </section>

      </div>
    </div>
  );
}

export default Hub;
