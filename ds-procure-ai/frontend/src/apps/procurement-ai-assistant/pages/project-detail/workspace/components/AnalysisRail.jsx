import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Spinner } from "@/components/ui/spinner";

import { API_BASE } from "../../../../../../services/api";
import { kbIsBuilding, kbStatusCopy } from "../kbStatus";
import { xlsxIsFilled, xlsxIsWritten } from "../packStatus";

function packHref(kind, packs, downloadPath) {
  const fromRoute = downloadPath?.(kind);
  if (fromRoute) return `${API_BASE}${fromRoute}`;
  const href = packs?.[kind]?.href;
  return href ? `${API_BASE}${href}` : "";
}

function HitlRail({ insights, skippedGaps, busy, onSkipGaps, onBuild, onAddFile, downloadPath }) {
  const decision = insights?.decision || {};
  const packs = insights?.packs || {};
  const missing = (insights?.requirements?.items || []).filter((item) => item.status === "missing");
  const xlsxReady = xlsxIsFilled(packs.xlsx?.status);
  const xlsxWritten = xlsxIsWritten(packs.xlsx?.status);
  const pptReady = packs.ppt?.status === "ready";
  const fileCount = insights?.file_count || 0;
  const xlsxHref = packHref("xlsx", packs, downloadPath);
  const pptHref = packHref("ppt", packs, downloadPath);
  const kbStatus = insights?.kb_status || "empty";
  const building = kbIsBuilding(kbStatus);
  const failed = kbStatus === "failed";

  let step = "upload";
  if (fileCount > 0) step = "kb";
  if (failed) {
    step = "kb";
  } else if (!building && fileCount > 0) {
    step = "gaps";
    if (skippedGaps || missing.length === 0) step = "xlsx";
    if (xlsxReady) step = "ppt";
    if (pptReady) step = "done";
  }

  const steps = [
    { id: "upload", label: "Create + files" },
    { id: "kb", label: "Knowledge base" },
    { id: "gaps", label: "Missing docs" },
    { id: "xlsx", label: "Comparison Excel" },
    { id: "ppt", label: "SteerCo PPT" },
  ];
  const currentIndex = ["upload", "kb", "gaps", "xlsx", "ppt", "done"].indexOf(step);

  return (
    <div className="ws-hitl">
      <ol className="ws-hitl-steps">
        {steps.map((item, index) => {
          let className = "";
          if (index < currentIndex) className = "done";
          else if (step === "done" && index === steps.length - 1) className = "done";
          else if (index === currentIndex) className = "current";
          return (
            <li key={item.id} className={className}>
              <span>{index + 1}</span>
              {item.label}
              {item.id === "kb" && building ? <Spinner /> : null}
            </li>
          );
        })}
      </ol>

      {step === "kb" && (building || failed) ? (
        <Card size="sm">
          <CardHeader>
            <CardTitle>Knowledge base</CardTitle>
            <CardDescription>
              {kbStatusCopy(kbStatus, insights?.kb_message) ||
                (failed ? "Knowledge base build failed." : "Building knowledge base...")}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex items-center gap-2 pb-(--card-spacing)">
            {building ? <Spinner /> : null}
            <Badge variant={failed ? "destructive" : "secondary"}>
              {failed ? "Failed" : "Building"}
            </Badge>
          </CardContent>
        </Card>
      ) : null}

      {step === "gaps" && missing.length > 0 && (
        <article className="ws-insight-card pack">
          <header>
            <span>HITL</span>
            <strong>{missing.length} missing</strong>
          </header>
          <p>Upload the remaining files, or continue with gaps marked missing. Packs stay draft.</p>
          <ul className="ws-gap-list">
            {missing.map((item) => (
              <li key={item.checklist_key} className="block">
                <span>{item.label}</span>
                <em>missing</em>
              </li>
            ))}
          </ul>
          <div className="ws-pack-actions">
            <button type="button" className="ws-pack-btn" onClick={onAddFile}>
              Upload remaining
            </button>
            <button type="button" className="ws-pack-link" onClick={onSkipGaps}>
              Continue with gaps
            </button>
          </div>
        </article>
      )}

      {step === "xlsx" && !xlsxWritten && (
        <article className="ws-insight-card pack">
          <header>
            <span>Permission</span>
            <strong>Excel</strong>
          </header>
          <p>{decision.summary || "Build the comparison matrix from parsed files. Humans award."}</p>
          <div className="ws-pack-actions">
            <button type="button" className="ws-pack-btn" disabled={busy === "xlsx"} onClick={() => onBuild("xlsx")}>
              {busy === "xlsx" ? "Building..." : "Yes, build comparison"}
            </button>
          </div>
        </article>
      )}

      {step === "xlsx" && xlsxWritten && !xlsxReady && (
        <article className="ws-insight-card pack">
          <header>
            <span>Template</span>
            <strong>Excel</strong>
          </header>
          <p>
            {packs.xlsx?.error ||
              "Workbook written, but vendor evidence was not persisted. Review the template or rebuild after the knowledge base is ready."}
          </p>
          <div className="ws-pack-actions">
            {xlsxHref ? (
              <a className="ws-pack-link" href={xlsxHref}>
                Download template
              </a>
            ) : null}
            <button type="button" className="ws-pack-btn" disabled={busy === "xlsx"} onClick={() => onBuild("xlsx")}>
              {busy === "xlsx" ? "Building..." : "Rebuild comparison"}
            </button>
          </div>
        </article>
      )}

      {xlsxReady && !pptReady && (
        <article className="ws-insight-card pack">
          <header>
            <span>Permission</span>
            <strong>SteerCo</strong>
          </header>
          <p>Review the Excel first. PPT numbers come only from named Excel fields.</p>
          <div className="ws-pack-actions">
            {xlsxHref ? (
              <a className="ws-pack-link" href={xlsxHref}>
                Review Excel
              </a>
            ) : null}
            <button type="button" className="ws-pack-btn" disabled={busy === "ppt"} onClick={() => onBuild("ppt")}>
              {busy === "ppt" ? "Building..." : "Yes, build SteerCo"}
            </button>
          </div>
        </article>
      )}

      {pptReady && pptHref && (
        <article className="ws-insight-card pack">
          <header>
            <span>Ready</span>
            <strong>Packs</strong>
          </header>
          <div className="ws-pack-actions">
            {xlsxHref ? (
              <a className="ws-pack-link" href={xlsxHref}>
                Download Excel
              </a>
            ) : null}
            <a className="ws-pack-link" href={pptHref}>
              Download PPT
            </a>
          </div>
        </article>
      )}
    </div>
  );
}

function AnalysisRail({
  open,
  onOpenChange,
  insights,
  error,
  skippedGaps,
  busy,
  onSkipGaps,
  onBuild,
  onAddFile,
  downloadPath,
}) {
  return (
    <Collapsible open={open} onOpenChange={onOpenChange} className="ws-chat-analysis">
      <CollapsibleTrigger className="ws-analysis-toggle" type="button">
        Analysis
        <span>{open ? "Hide" : "Show"}</span>
      </CollapsibleTrigger>
      <CollapsibleContent className="ws-analysis-panel">
        {error ? <p className="ws-insight-meta">{error}</p> : null}
        <article className="ws-insight-card">
          <header>
            <span>Process</span>
            <strong>{insights?.process_label || "Unset"}</strong>
          </header>
          <p>
            {insights?.owner_entity || "Owner unset"}
            {" · "}
            {insights?.file_count || 0} files
            {" · "}
            {insights?.knowledge_pct ?? 0}% coverage
          </p>
        </article>
        <HitlRail
          insights={insights}
          skippedGaps={skippedGaps}
          busy={busy}
          onSkipGaps={onSkipGaps}
          onBuild={onBuild}
          onAddFile={onAddFile}
          downloadPath={downloadPath}
        />
        {(insights?.vendors || []).map((vendor) => (
          <article key={vendor.vendor_id} className="ws-insight-card">
            <header>
              <span>Vendor</span>
              <strong>{vendor.name}</strong>
            </header>
            <p>{vendor.headline}</p>
          </article>
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}

export default AnalysisRail;
