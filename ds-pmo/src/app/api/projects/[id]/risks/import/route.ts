import { withHandler, createAuditLog } from "@/lib/api-handler";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { NextResponse } from "next/server";
import ExcelJS from "exceljs";
import { deleteRisksForProject, createRisksBatch, type RiskInput } from "@/lib/db/risks";
import { updateProjectRow } from "@/lib/db/projects";
import { deleteRows, insertRows } from "@/lib/db/query-builder";
import { toRow } from "@/lib/db/rowmap";

/* ── Shared types (exported for frontend) ─────────────────────── */

export interface ParsedRisk {
  num: number;
  type: string;
  description: string;
  originator: string;
  probability: number;
  costImpactRating: number;
  timeImpactRating: number;
  scopeImpactRating: number;
  weight: number;
  maxImpact: number;
  costK: number | null;
  ponderedCost: number | null;
  timeImpactDays: number | null;
  category: string;
  status: string;
  owner: string;
  comments: string;
  actions: ParsedAction[];
}

export interface ParsedAction {
  riskNum: number;
  actionNum: number;
  riskDescription: string;
  action: string;
  response: string;
  assignedTo: string;
  status: string;
  plannedEnd: string | null;
  comments: string;
  parentWeight: number;
}

export interface RiacSummary {
  totalRisks: number;
  totalActions: number;
  openRisks: number;
  closedRisks: number;
  issues: number;
  highRisks: number;
  moderateRisks: number;
  lowRisks: number;
  totalCostAtRisk: number;
  maxTimeImpact: number;
  risksIdentified: number;
  risksQuantified: number;
}

export interface ParsedScopeChange {
  description: string;
  submittedDate: string;
  impactCost: string;
  impactSchedule: string;
  impactCostValue: number | null;
  impactScheduleValue: number | null;
  status: string;
}

export interface RiacPreview {
  valid: boolean;
  error?: string;
  summary: RiacSummary;
  allRisks: ParsedRisk[];
  allActions: ParsedAction[];
  top5Risks: ParsedRisk[];
  top5Actions: ParsedAction[];
  tiedRisks: ParsedRisk[];
  tiedActions: ParsedAction[];
  guaranteedSlots: number;
  slotsToFill: number;
  scopeChanges: ParsedScopeChange[];
}

/* ── File validation constants ────────────────────────────────── */

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB
const ALLOWED_MIME_TYPES = [
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.ms-excel",
];
const ALLOWED_EXTENSIONS = [".xlsx", ".xls"];

/* ── Flexible header detection ────────────────────────────────── */

const RISK_COL_PATTERNS: Record<string, RegExp> = {
  number:       /n[°o#º]/i,
  type:         /^type$/i,
  description:  /^description$/i,
  originator:   /^originator$/i,
  probability:  /^probability$/i,
  costImpact:   /^cost\s*impact$/i,
  timeImpact:   /^time\s*impact$/i,
  scopeImpact:  /scope.*quality|quality.*impact/i,
  weight:       /^weight$/i,
  maxImpact:    /^max\s*impact$/i,
  costK:        /cost\s*impact.*k[€e]/i,
  ponderedCost: /pondered/i,
  timeImpactDays: /time\s*impact.*day/i,
  category:     /^category$/i,
  status:       /^status$/i,
  owner:        /^owner$/i,
  comments:     /^comments?$/i,
};

const ACTION_COL_PATTERNS: Record<string, RegExp> = {
  riskNum:      /^ri?\s*n[°o#º]?$/i,
  description:  /^description$/i,
  actionNum:    /action\s*n[°o#º]/i,
  action:       /^action$/i,
  response:     /^response$/i,
  assignedTo:   /assigned\s*to/i,
  status:       /^status$/i,
  plannedEnd:   /planned\s*end/i,
  comments:     /^comments?$/i,
};

const SCOPE_CHANGE_COL_PATTERNS: Record<string, RegExp> = {
  title: /^title$/i,
  description: /^description$/i,
  identificationDate: /identification\s*date|submitted\s*date|^date$/i,
  impactCost: /^impact\s+(estimated\s+)?k[€e]/i,
  impactDays: /^impact\s+(estimated\s+)?day/i,
  impact: /^impact$/i,
  status: /change\s*status|^status$/i,
  comment: /^comments?$/i,
};

const REQUIRED_SCOPE_CHANGE_COLS = ["description"];
const REQUIRED_RISK_COLS = ["description", "probability", "status", "owner"];
const REQUIRED_ACTION_COLS = ["action", "status", "assignedTo"];

function normalizeHeader(val: unknown): string {
  return String(val ?? "").replace(/[\r\n]+/g, " ").trim();
}

function findHeaderRow(
  rows: unknown[][],
  patterns: Record<string, RegExp>,
  requiredCols: string[],
  scanRows = 15,
): { rowIdx: number; colMap: Record<string, number> } | null {
  let bestMatch: { rowIdx: number; colMap: Record<string, number>; score: number } | null = null;

  for (let r = 0; r < Math.min(rows.length, scanRows); r++) {
    const row = rows[r];
    if (!row || !Array.isArray(row)) continue;

    const colMap: Record<string, number> = {};
    for (let c = 0; c < row.length; c++) {
      const header = normalizeHeader(row[c]);
      if (!header) continue;
      for (const [name, pattern] of Object.entries(patterns)) {
        if (pattern.test(header) && !(name in colMap)) {
          colMap[name] = c;
        }
      }
    }

    const hasRequired = requiredCols.every((col) => col in colMap);
    const score = Object.keys(colMap).length;

    if (hasRequired && (!bestMatch || score > bestMatch.score)) {
      bestMatch = { rowIdx: r, colMap, score };
    }
  }

  return bestMatch ? { rowIdx: bestMatch.rowIdx, colMap: bestMatch.colMap } : null;
}

/* ── ExcelJS adapter ───────────────────────────────────────────
   ExcelJS returns rich cell objects (Date, {richText}, {hyperlink},
   {formula, result}, error, etc.). Flatten each cell to a plain
   primitive so downstream helpers stay simple. */

function flattenCell(v: unknown): unknown {
  if (v == null) return "";
  if (v instanceof Date) return v;
  if (typeof v !== "object") return v;

  const o = v as Record<string, unknown>;
  if (Array.isArray(o.richText)) {
    return (o.richText as { text?: string }[]).map((rt) => rt.text ?? "").join("");
  }
  if ("formula" in o) return o.result ?? "";
  if (typeof o.text === "string") return o.text;
  if (typeof o.hyperlink === "string") return o.hyperlink;
  if (typeof o.error === "string") return o.error;
  return String(v);
}

function sheetToRows(ws: ExcelJS.Worksheet): unknown[][] {
  const out: unknown[][] = [];
  ws.eachRow({ includeEmpty: true }, (row, rowNumber) => {
    // row.values is a 1-based sparse array; element 0 is unused.
    const values = row.values as unknown[];
    const flat: unknown[] = [];
    for (let c = 1; c < values.length; c++) {
      flat.push(flattenCell(values[c]));
    }
    out[rowNumber - 1] = flat;
  });
  for (let i = 0; i < out.length; i++) {
    if (!out[i]) out[i] = [];
  }
  return out;
}

function findSheet(workbook: ExcelJS.Workbook, patterns: RegExp[]): ExcelJS.Worksheet | null {
  return workbook.worksheets.find((ws) => patterns.some((p) => p.test(ws.name))) ?? null;
}

/* ── Value helpers ─────────────────────────────────────────────── */

function toNum(val: unknown): number {
  if (val == null || val === "") return 0;
  const n = typeof val === "number" ? val : parseFloat(String(val).replace(/[^\d.\-]/g, ""));
  return isNaN(n) ? 0 : n;
}

function toNumOrNull(val: unknown): number | null {
  if (val == null || val === "") return null;
  const n = typeof val === "number" ? val : parseFloat(String(val).replace(/[^\d.\-]/g, ""));
  return isNaN(n) ? null : n;
}

function toStr(val: unknown): string {
  if (val == null) return "";
  return String(val).trim();
}

function toDateStr(val: unknown): string | null {
  if (val == null || val === "") return null;
  if (val instanceof Date) {
    return isNaN(val.getTime()) ? null : val.toISOString().slice(0, 10);
  }
  const s = String(val).trim();
  if (!s) return null;
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : d.toISOString().slice(0, 10);
}

/* ── Status / category mapping ─────────────────────────────────── */

function mapStatus(raw: string): "OPEN" | "MITIGATING" | "CLOSED" | "ACCEPTED" {
  const s = raw.toLowerCase().trim();
  if (s.includes("close")) return "CLOSED";
  if (s.includes("progress") || s.includes("delay")) return "MITIGATING";
  if (s.includes("accept")) return "ACCEPTED";
  return "OPEN";
}

function mapRiskType(type: string): "RISK" | "ISSUE" {
  return type.toLowerCase() === "issue" ? "ISSUE" : "RISK";
}

function mapImpact(weight: number): "HIGH" | "MODERATE" | "LOW" {
  if (weight >= 8) return "HIGH";
  if (weight >= 3) return "MODERATE";
  return "LOW";
}

function mapScopeChangeStatus(raw: string): "OPEN" | "APPROVED" | "ON_HOLD" | "CANCELLED" {
  const s = raw.toLowerCase().trim();
  if (s.includes("hold")) return "ON_HOLD";
  if (s.includes("cancel") || s.includes("closed") || s.includes("reject")) return "CANCELLED";
  if (s.includes("approv") || s.includes("validated") || s.includes("accepted")) return "APPROVED";
  return "OPEN";
}

/* ── Parse sheets ──────────────────────────────────────────────── */

function parseRiskRows(
  rows: unknown[][],
  headerInfo: { rowIdx: number; colMap: Record<string, number> },
): ParsedRisk[] {
  const { rowIdx, colMap } = headerInfo;
  const risks: ParsedRisk[] = [];

  for (let r = rowIdx + 1; r < rows.length; r++) {
    const row = rows[r];
    if (!row || !Array.isArray(row)) continue;

    const description = toStr(row[colMap.description]);
    if (!description) continue;

    const probability = toNum(row[colMap.probability]);
    const costImpact = toNum(row[colMap.costImpact]);
    const timeImpact = toNum(row[colMap.timeImpact]);
    const scopeImpact = colMap.scopeImpact != null ? toNum(row[colMap.scopeImpact]) : 0;
    const maxImpact = colMap.maxImpact != null
      ? toNum(row[colMap.maxImpact])
      : Math.max(costImpact, timeImpact, scopeImpact);
    const weight = colMap.weight != null
      ? toNum(row[colMap.weight])
      : probability * maxImpact;

    risks.push({
      num: colMap.number != null ? toNum(row[colMap.number]) : r - rowIdx,
      type: toStr(row[colMap.type] ?? "Risk"),
      description,
      originator: toStr(row[colMap.originator]),
      probability,
      costImpactRating: costImpact,
      timeImpactRating: timeImpact,
      scopeImpactRating: scopeImpact,
      weight,
      maxImpact,
      costK: colMap.costK != null ? toNumOrNull(row[colMap.costK]) : null,
      ponderedCost: colMap.ponderedCost != null ? toNumOrNull(row[colMap.ponderedCost]) : null,
      timeImpactDays: colMap.timeImpactDays != null ? toNumOrNull(row[colMap.timeImpactDays]) : null,
      category: toStr(row[colMap.category]),
      status: toStr(row[colMap.status] ?? "Open"),
      owner: toStr(row[colMap.owner]),
      comments: toStr(row[colMap.comments]),
      actions: [],
    });
  }

  return risks;
}

function parseActionRows(
  rows: unknown[][],
  headerInfo: { rowIdx: number; colMap: Record<string, number> },
): ParsedAction[] {
  const { rowIdx, colMap } = headerInfo;
  const actions: ParsedAction[] = [];

  for (let r = rowIdx + 1; r < rows.length; r++) {
    const row = rows[r];
    if (!row || !Array.isArray(row)) continue;

    const action = toStr(row[colMap.action]);
    if (!action) continue;

    actions.push({
      riskNum: colMap.riskNum != null ? toNum(row[colMap.riskNum]) : 0,
      actionNum: colMap.actionNum != null ? toNum(row[colMap.actionNum]) : r - rowIdx,
      riskDescription: toStr(row[colMap.description]),
      action,
      response: toStr(row[colMap.response]),
      assignedTo: toStr(row[colMap.assignedTo]),
      status: toStr(row[colMap.status]),
      plannedEnd: colMap.plannedEnd != null ? toDateStr(row[colMap.plannedEnd]) : null,
      comments: toStr(row[colMap.comments]),
      parentWeight: 0,
    });
  }

  return actions;
}

function parseScopeChangeRows(
  rows: unknown[][],
  headerInfo: { rowIdx: number; colMap: Record<string, number> },
): ParsedScopeChange[] {
  const { rowIdx, colMap } = headerInfo;
  const changes: ParsedScopeChange[] = [];

  for (let r = rowIdx + 1; r < rows.length; r++) {
    const row = rows[r];
    if (!row || !Array.isArray(row)) continue;

    // Use title if available, fall back to description
    const title = colMap.title != null ? toStr(row[colMap.title]) : "";
    const desc = colMap.description != null ? toStr(row[colMap.description]) : "";
    const description = title || desc;
    if (!description) continue;

    // Extract date
    const submittedDate = colMap.identificationDate != null
      ? toDateStr(row[colMap.identificationDate]) ?? ""
      : "";

    // Extract impact cost and schedule — populate BOTH the display string
    // (legacy) and the numeric column (used by aggregation queries).
    let impactCost = "";
    let impactSchedule = "";
    let impactCostValue: number | null = null;
    let impactScheduleValue: number | null = null;
    if (colMap.impactCost != null) {
      const costVal = toNumOrNull(row[colMap.impactCost]);
      if (costVal != null) {
        impactCost = `${costVal} k€`;
        impactCostValue = costVal;
      }
    } else if (colMap.impact != null) {
      // Fallback: single "Impact" column maps to impactCost as free-text
      impactCost = toStr(row[colMap.impact]);
    }
    if (colMap.impactDays != null) {
      const dayVal = toNumOrNull(row[colMap.impactDays]);
      if (dayVal != null) {
        impactSchedule = `${dayVal} days`;
        impactScheduleValue = Math.round(dayVal);
      }
    }

    changes.push({
      description: title && desc ? `${title}: ${desc}` : description,
      submittedDate,
      impactCost,
      impactSchedule,
      impactCostValue,
      impactScheduleValue,
      status: colMap.status != null ? toStr(row[colMap.status]) : "Open",
    });
  }

  return changes;
}

/* ── Ranking with tie detection ────────────────────────────────── */

function rankWithTies<T>(
  items: T[],
  scoreFn: (item: T) => number,
  limit: number,
): { guaranteed: T[]; tied: T[]; slotsToFill: number } {
  if (items.length <= limit) {
    return { guaranteed: items, tied: [], slotsToFill: 0 };
  }

  const sorted = [...items].sort((a, b) => scoreFn(b) - scoreFn(a));
  const cutoffScore = scoreFn(sorted[limit - 1]);

  const guaranteed = sorted.filter((item) => scoreFn(item) > cutoffScore);
  const tied = sorted.filter((item) => scoreFn(item) === cutoffScore);
  const slotsToFill = limit - guaranteed.length;

  if (tied.length <= slotsToFill) {
    return { guaranteed: sorted.slice(0, limit), tied: [], slotsToFill: 0 };
  }

  return { guaranteed, tied, slotsToFill };
}

/* ── Main parse function ───────────────────────────────────────── */

function emptySummary(): RiacSummary {
  return {
    totalRisks: 0, totalActions: 0, openRisks: 0, closedRisks: 0,
    issues: 0, highRisks: 0, moderateRisks: 0, lowRisks: 0,
    totalCostAtRisk: 0, maxTimeImpact: 0, risksIdentified: 0, risksQuantified: 0,
  };
}

function invalidPreview(error: string): RiacPreview {
  return {
    valid: false,
    error,
    summary: emptySummary(),
    allRisks: [], allActions: [], top5Risks: [], top5Actions: [],
    tiedRisks: [], tiedActions: [],
    guaranteedSlots: 0, slotsToFill: 0, scopeChanges: [],
  };
}

async function parseRiac(buffer: ArrayBuffer): Promise<RiacPreview> {
  const workbook = new ExcelJS.Workbook();
  // exceljs typings demand its own minimal Buffer shape; ArrayBuffer is
  // accepted at runtime (jszip handles it), so widen via unknown.
  await workbook.xlsx.load(buffer as unknown as ExcelJS.Buffer);

  const risksSheet = findSheet(workbook, [/risk/i, /r[&\s]*i/i]);
  if (!risksSheet) {
    return invalidPreview(
      "Could not find a 'Risks-Issues LOG' sheet. Make sure the RIAC file follows the standard template.",
    );
  }

  const riskRows = sheetToRows(risksSheet);
  const riskHeader = findHeaderRow(riskRows, RISK_COL_PATTERNS, REQUIRED_RISK_COLS);
  if (!riskHeader) {
    return invalidPreview(
      "Could not find valid risk headers. Expected columns: Description, Probability, Status, Owner.",
    );
  }

  const actionsSheet = findSheet(workbook, [/action/i]);
  const actionRows = actionsSheet ? sheetToRows(actionsSheet) : [];
  const actionHeader = actionRows.length > 0
    ? findHeaderRow(actionRows, ACTION_COL_PATTERNS, REQUIRED_ACTION_COLS)
    : null;

  // Parse scope changes sheet (optional)
  const scopeChangesSheet = findSheet(workbook, [/scope.*change/i, /change/i]);
  let scopeChanges: ParsedScopeChange[] = [];
  if (scopeChangesSheet) {
    const scRows = sheetToRows(scopeChangesSheet);
    const scHeader = findHeaderRow(scRows, SCOPE_CHANGE_COL_PATTERNS, REQUIRED_SCOPE_CHANGE_COLS);
    if (scHeader) {
      scopeChanges = parseScopeChangeRows(scRows, scHeader);
    }
  }

  const allRisks = parseRiskRows(riskRows, riskHeader);
  const allActions = actionHeader ? parseActionRows(actionRows, actionHeader) : [];

  if (allRisks.length === 0) {
    return invalidPreview(
      "No risk rows found in the file. Check that data starts below the header row.",
    );
  }

  const riskMap = new Map<number, ParsedRisk>();
  for (const r of allRisks) riskMap.set(r.num, r);

  for (const a of allActions) {
    const parent = riskMap.get(a.riskNum);
    if (parent) {
      parent.actions.push(a);
      a.parentWeight = parent.weight;
    }
  }

  const isIssue = (r: ParsedRisk) => r.type.toLowerCase() === "issue";
  const isClosed = (s: string) => s.toLowerCase().includes("close");

  const openRisks = allRisks.filter((r) => !isClosed(r.status));
  const closedRisks = allRisks.filter((r) => isClosed(r.status));
  const issues = allRisks.filter(isIssue);
  const openActions = allActions.filter((a) => !isClosed(a.status));

  const openNonIssues = openRisks.filter((r) => !isIssue(r));
  const highRisks = openNonIssues.filter((r) => r.weight >= 8);
  const moderateRisks = openNonIssues.filter((r) => r.weight >= 3 && r.weight < 8);
  const lowRisks = openNonIssues.filter((r) => r.weight < 3);

  const totalCostAtRisk = allRisks.reduce((sum, r) => sum + (r.ponderedCost ?? 0), 0);
  const maxTimeImpact = Math.max(0, ...allRisks.map((r) => r.timeImpactDays ?? 0));
  const quantified = allRisks.filter(
    (r) => r.probability > 0 && (r.costK != null || r.timeImpactDays != null),
  );

  const summary: RiacSummary = {
    totalRisks: allRisks.length,
    totalActions: allActions.length,
    openRisks: openRisks.length,
    closedRisks: closedRisks.length,
    issues: issues.length,
    highRisks: highRisks.length,
    moderateRisks: moderateRisks.length,
    lowRisks: lowRisks.length,
    totalCostAtRisk: Math.round(totalCostAtRisk),
    maxTimeImpact,
    risksIdentified: allRisks.length,
    risksQuantified: quantified.length,
  };

  const { guaranteed: top5Risks, tied: tiedRisks, slotsToFill } =
    rankWithTies(openRisks, (r) => r.weight, 5);

  const { guaranteed: top5Actions, tied: tiedActions } = rankWithTies(
    openActions.filter((a) => a.parentWeight > 0),
    (a) => a.parentWeight,
    5,
  );

  return {
    valid: true,
    summary,
    allRisks,
    allActions,
    top5Risks,
    top5Actions,
    tiedRisks,
    tiedActions,
    guaranteedSlots: top5Risks.length,
    slotsToFill,
    scopeChanges,
  };
}

function extractClause(text: string, type: "if" | "due to" | "then"): string | null {
  if (!text) return null;
  const patterns: Record<string, RegExp> = {
    if: /\bif\s+(.+?)(?:\s*,?\s*(?:due\s+to|then)\b|$)/i,
    "due to": /\bdue\s+to\s+(.+?)(?:\s*,?\s*then\b|$)/i,
    then: /\bthen\s+(.+)$/i,
  };
  const match = text.match(patterns[type]);
  return match ? match[1].trim() : null;
}

/* ═══════════════════════════════════════════════════════════════════
   POST handler — preview (FormData) or save (JSON)
   Uses withHandler for auth + project access; body parsing is custom
   since this route handles both multipart and JSON.
   ═══════════════════════════════════════════════════════════════════ */

export const POST = withHandler<undefined, { id: string }>(
  { projectAccess: true, rateLimit: RATE_LIMITS.upload },
  async ({ req, user, params }) => {
    const contentType = req.headers.get("content-type") ?? "";

    /* ── PREVIEW mode (FormData with file) ──────────────────────── */
    if (contentType.includes("multipart/form-data")) {
      const formData = await req.formData();
      const file = formData.get("file") as File;
      if (!file) {
        return NextResponse.json({ error: "File is required" }, { status: 400 });
      }

      // File validation: size
      if (file.size > MAX_FILE_SIZE) {
        return NextResponse.json(
          { error: "File too large. Maximum size is 10MB." },
          { status: 400 },
        );
      }

      // File validation: MIME type
      if (file.type && !ALLOWED_MIME_TYPES.includes(file.type)) {
        const name = file.name?.toLowerCase() ?? "";
        if (!ALLOWED_EXTENSIONS.some((ext) => name.endsWith(ext))) {
          return NextResponse.json(
            { error: "Invalid file type. Only Excel files (.xlsx, .xls) are accepted." },
            { status: 400 },
          );
        }
      }

      // File validation: extension
      const fileName = file.name?.toLowerCase() ?? "";
      if (!ALLOWED_EXTENSIONS.some((ext) => fileName.endsWith(ext))) {
        return NextResponse.json(
          { error: "Invalid file extension. Only .xlsx and .xls files are accepted." },
          { status: 400 },
        );
      }

      const buffer = await file.arrayBuffer();
      const result = await parseRiac(buffer);

      if (!result.valid) {
        return NextResponse.json({ error: result.error }, { status: 422 });
      }

      return NextResponse.json(result);
    }

    /* ── SAVE mode (JSON) — risks and/or scope changes ────────── */
    let body: {
      risks?: ParsedRisk[];
      actions?: ParsedAction[];
      summary?: RiacSummary;
      scopeChanges?: ParsedScopeChange[];
    };
    try {
      body = await req.json();
    } catch {
      return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
    }

    const hasRisks = Array.isArray(body.risks) && body.risks.length > 0;
    const hasChanges = Array.isArray(body.scopeChanges) && body.scopeChanges.length > 0;

    if (!hasRisks && !hasChanges) {
      return NextResponse.json(
        { error: "Nothing to import — provide risks and/or scope changes" },
        { status: 400 },
      );
    }

    /* ── Import risks (if provided) ────────────────────────────── */
    let importedRiskCount = 0;
    if (hasRisks) {
      const risks = body.risks!;
      const actions = body.actions ?? [];

      await deleteRisksForProject(params.id);

      const riskInputs: RiskInput[] = risks.map((r) => {
        const riskActions = actions.filter((a) => a.riskNum === r.num) ?? r.actions ?? [];
        const counterMeasures =
          riskActions
            .map(
              (a) =>
                `[${a.response || "Action"}] ${a.action}${a.assignedTo ? ` (${a.assignedTo})` : ""}`,
            )
            .join("\n") || null;

        // Normalize probability: RIAC uses 0-10 scale, we store 0-100
        const normalizedProb = r.probability ? Math.round(r.probability * 10) : null;

        // Derive completion date from earliest planned end among actions
        const actionDates = riskActions
          .map((a) => a.plannedEnd)
          .filter((d): d is string => d != null && d !== "");
        const completionDate = actionDates.length > 0
          ? new Date(actionDates.sort().pop()!) // latest planned end
          : null;

        return {
          projectId: params.id,
          riskNumber: r.num,
          type: mapRiskType(r.type),
          riskStatement: r.description,
          ifClause: extractClause(r.description, "if"),
          dueToClause: extractClause(r.description, "due to"),
          thenClause: extractClause(r.description, "then"),
          impact: mapImpact(r.weight),
          category: r.category || null,
          probability: normalizedProb,
          costImpact: r.costK,
          timeImpact: r.timeImpactDays != null ? r.timeImpactDays : null,
          weight: r.weight || null,
          counterMeasures,
          responseStrategy: riskActions[0]?.response || null,
          completionDate: completionDate && !isNaN(completionDate.getTime()) ? completionDate : null,
          ownerName: r.owner || null,
          status: mapStatus(r.status),
          comments: r.comments || null,
        };
      });

      await createRisksBatch(riskInputs);

      importedRiskCount = riskInputs.length;

      // Autofill the editable risk-summary inputs on the project from the
      // RIAC summary (decoupled from the Risk table — see risk-counts-design).
      const projectUpdate: {
        risksIssuesCount?: number;
        risksHighCount?: number;
        risksModerateCount?: number;
        risksLowCount?: number;
        risksIdentifiedCount?: number;
        risksQuantifiedCount?: number;
        totalCostAtRisk?: number;
        totalTimeImpact?: number;
      } = {};

      if (body.summary) {
        projectUpdate.risksIssuesCount = body.summary.issues;
        projectUpdate.risksHighCount = body.summary.highRisks;
        projectUpdate.risksModerateCount = body.summary.moderateRisks;
        projectUpdate.risksLowCount = body.summary.lowRisks;
        projectUpdate.risksIdentifiedCount = body.summary.risksIdentified;
        projectUpdate.risksQuantifiedCount = body.summary.risksQuantified;
        projectUpdate.totalCostAtRisk = body.summary.totalCostAtRisk;
        projectUpdate.totalTimeImpact = body.summary.maxTimeImpact;
      }

      if (Object.keys(projectUpdate).length > 0) {
        await updateProjectRow(params.id, projectUpdate);
      }
    }

    /* ── Import scope changes (if provided) ────────────────────── */
    let importedScopeChanges = 0;
    if (hasChanges) {
      const changes = body.scopeChanges!;
      await deleteRows("scope_changes", [{ type: "eq", column: "project_id", value: params.id }]);
      const now = new Date();
      await insertRows(
        "scope_changes",
        changes.map((sc) =>
          toRow({
            projectId: params.id,
            description: sc.description,
            submittedDate: sc.submittedDate ? new Date(sc.submittedDate) : null,
            impactCost: sc.impactCost || null,
            impactSchedule: sc.impactSchedule || null,
            impactCostValue: sc.impactCostValue ?? null,
            impactScheduleValue: sc.impactScheduleValue ?? null,
            status: mapScopeChangeStatus(sc.status),
            createdAt: now,
            updatedAt: now,
          }),
        ),
      );
      importedScopeChanges = changes.length;
    }

    /* ── Audit log ─────────────────────────────────────────────── */
    const auditChanges: Record<string, { old: null; new: unknown }> = {
      source: { old: null, new: "RIAC" },
    };
    if (importedRiskCount > 0) {
      auditChanges.importedRisks = { old: null, new: importedRiskCount };
      auditChanges.totalRisksInFile = { old: null, new: body.summary?.totalRisks ?? 0 };
    }
    if (importedScopeChanges > 0) {
      auditChanges.importedScopeChanges = { old: null, new: importedScopeChanges };
    }

    await createAuditLog({
      userId: user.id,
      projectId: params.id,
      action: "RISK_IMPORT",
      entity: hasRisks ? "Risk" : "ScopeChange",
      entityId: params.id,
      changes: auditChanges,
    });

    return NextResponse.json(
      { success: true, importedRisks: importedRiskCount, importedScopeChanges },
      { status: 201 },
    );
  },
);
