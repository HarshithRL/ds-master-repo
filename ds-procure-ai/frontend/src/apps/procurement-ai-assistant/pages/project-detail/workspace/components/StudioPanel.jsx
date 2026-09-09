import { Spinner } from "@/components/ui/spinner";

import { kbIsBuilding } from "../kbStatus";

const STUDIO_TABS = ["Evidence", "Context", "Graph"];

function KnowledgeGraph({ projectName, graph }) {
  return (
    <div className="ws-graph">
      <svg viewBox="0 0 360 320" className="ws-graph-svg" aria-hidden="true">
        {graph.edges.map((edge, index) => (
          <line
            key={`edge-${index}`}
            x1={edge.x1}
            y1={edge.y1}
            x2={edge.x2}
            y2={edge.y2}
            className="ws-graph-edge"
          />
        ))}
        {graph.edgeLabels.map((label) => (
          <text key={label.text} x={label.x} y={label.y} className="ws-graph-label">
            {label.text}
          </text>
        ))}
      </svg>
      {graph.nodes.map((node) => (
        <div key={node.id} className={`ws-graph-node ${node.className}`}>
          {node.labelKey === "projectName" ? projectName : node.label}
        </div>
      ))}
    </div>
  );
}

function StudioPanel({ projectName, graph, insights, tab, onTab, onCollapse }) {
  const evidence = insights?.vendors?.flatMap((vendor) =>
    (vendor.evidence || []).map((item) => ({ vendor: vendor.name, ...item })),
  );

  return (
    <aside className="ws-studio">
      <div className="ws-panel-header">
        <strong>STUDIO</strong>
        <button type="button" className="ws-sidebar-toggle" onClick={onCollapse} aria-label="Collapse studio">
          Hide
        </button>
      </div>
      <div className="ws-studio-tabs">
        {STUDIO_TABS.map((name) => (
          <button key={name} type="button" className={tab === name ? "active" : ""} onClick={() => onTab(name)}>
            {name}
          </button>
        ))}
      </div>
      <div className="ws-studio-body">
        {tab === "Graph" && <KnowledgeGraph projectName={projectName} graph={graph} />}
        {tab === "Context" && (
          <div className="ws-studio-placeholder">
            <p>
              {insights?.process_label || "Process unset"} · {insights?.owner_entity || "Owner unset"}
            </p>
            <p className="flex items-center gap-2 text-muted-foreground text-xs">
              {kbIsBuilding(insights?.kb_status) ? <Spinner /> : null}
              <span>
                KB {insights?.kb_status || "empty"} · {insights?.file_count || 0} files · {insights?.knowledge_pct ?? 0}%
              </span>
            </p>
          </div>
        )}
        {tab === "Evidence" && (
          <div className="ws-insight-list">
            {(evidence || []).length === 0 ? (
              <div className="ws-studio-placeholder">
                <p>Cited snippets appear after parse. No locator means missing, not zero.</p>
              </div>
            ) : (
              evidence.map((item) => (
                <article key={`${item.chunk_id}-${item.locator}`} className="ws-insight-card">
                  <header>
                    <span>{item.vendor}</span>
                    <strong>{item.locator}</strong>
                  </header>
                  <p>{item.quote || "No quote on this chunk."}</p>
                </article>
              ))
            )}
          </div>
        )}
      </div>
    </aside>
  );
}

export default StudioPanel;
