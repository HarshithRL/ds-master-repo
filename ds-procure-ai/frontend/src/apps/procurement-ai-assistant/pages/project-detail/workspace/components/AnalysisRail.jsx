import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";

import { API_BASE } from "../../../../../../services/api";
import { kbIsBuilding, kbStatusCopy } from "../kbStatus";
import { xlsxIsBuilding, xlsxIsFilled, xlsxIsWritten } from "../packStatus";

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
  const blockingMissing = missing.filter((item) => item.severity === "blocking");
  const optionalMissing = missing.filter((item) => item.severity !== "blocking");
  const xlsxReady = xlsxIsFilled(packs.xlsx?.status);
  // The run outlives the POST that starts it, so the button follows the polled
  // status rather than local click state.
  const xlsxBuilding = xlsxIsBuilding(packs.xlsx?.status);
  const xlsxBusy = busy === "xlsx" || xlsxBuilding;
  // Keep an earlier workbook downloadable while the next run is in flight.
  const xlsxWritten =
    xlsxIsWritten(packs.xlsx?.status) || (xlsxBuilding && Boolean(packs.xlsx?.filename));
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
    // Only blocking gaps gate. skippedGaps is per-mount state, so an optional
    // gap used to pin the rail on step 3 again after every reload.
    if (skippedGaps || blockingMissing.length === 0) step = "xlsx";
    if (xlsxReady) step = "ppt";
    if (pptReady) step = "done";
  }

  const steps = [
    { id: "upload", label: "Create + files" },
    { id: "kb", label: "Knowledge base" },
    { id: "gaps", label: "Missing docs" },
    { id: "xlsx", label: "Comparison Excel" },
  ];
  const currentIndex = ["upload", "kb", "gaps", "xlsx", "done"].indexOf(step);

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
            <strong>{blockingMissing.length} blocking</strong>
          </header>
          <p>
            A comparison needs these. Upload them, or continue and the pack will record them as
            not supplied.
          </p>
          <ul className="ws-gap-list">
            {missing.map((item) => (
              <li
                key={item.checklist_key}
                className={item.severity === "blocking" ? "block" : "opt"}
              >
                <span>
                  {item.label}
                  {item.hint ? <small>{item.hint}</small> : null}
                </span>
                <em>{item.severity === "blocking" ? "required" : "optional"}</em>
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
          {optionalMissing.length > 0 ? (
            <ul className="ws-gap-list">
              {optionalMissing.map((item) => (
                <li key={item.checklist_key} className="opt">
                  <span>
                    {item.label}
                    {item.hint ? <small>{item.hint}</small> : null}
                  </span>
                  <em>not supplied</em>
                </li>
              ))}
            </ul>
          ) : null}
          <div className="ws-pack-actions">
            <button type="button" className="ws-pack-btn" disabled={xlsxBusy} onClick={() => onBuild("xlsx")}>
              {xlsxBusy ? "Building..." : "Yes, build comparison"}
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
              "Workbook written, but vendor evidence was not persisted. Download the template, or build the comparison once the knowledge base is ready."}
          </p>
          <div className="ws-pack-actions">
            {xlsxHref ? (
              <a className="ws-pack-link" href={xlsxHref}>
                Download template
              </a>
            ) : null}
            <button type="button" className="ws-pack-btn" disabled={xlsxBusy} onClick={() => onBuild("xlsx")}>
              {xlsxBusy ? "Building..." : "Build comparison"}
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
    <div className="ws-analysis-panel ws-analysis-tab">
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
    </div>
  );
}

export default AnalysisRail;
