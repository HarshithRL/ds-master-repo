// ─── Phase & Lifecycle Definitions ───────────────────────────────────

export interface Phase {
  key: string;
  phaseNumber: number;
  label: string;
  shortLabel: string;
  description: string;
  color: string;
  bgColor: string; // Tailwind class
  textColor: string; // Tailwind class
  stageGroup: "Pre-Project" | "Project Planning" | "Project Execution" | "Post Project" | "Closed";
}

export interface GatePosition {
  key: string; // gate key (RED, AMBER, etc.)
  at: number;  // position on the phase axis
}

export interface LifecycleDefinition {
  key: string;
  label: string;
  phases: Phase[];
  phaseGateMap: Record<string, string[]>;   // phase key → gate keys at end of that phase
  gatePositions: GatePosition[];            // where gates sit on the timeline
  defaultPhase: string;                     // initial phase for new projects
}

// ─── Gate Definitions (universal across all lifecycles) ──────────────

export interface Gate {
  key: string;
  label: string;
  description: string;
  color: string;
  bgColor: string; // Tailwind class
  reviews: string[]; // Review types/requirements
}

export const GATES: Gate[] = [
  { key: "RED",    label: "RED Gate",    description: "Business case review",                                            color: "#DC2626", bgColor: "bg-red-600",                      reviews: ["Business Case Review"] },
  { key: "AMBER",  label: "AMBER Gate",  description: "Project ready for opportunity",                                   color: "#F97316", bgColor: "bg-orange-500",                   reviews: ["Opportunity Readiness Review"] },
  { key: "GREEN",  label: "GREEN Gate",  description: "Project Maturity Review / Kick-off meeting / Opportunity CIC approval", color: "#22C55E", bgColor: "bg-green-500",              reviews: ["Project Maturity Review", "Kick-off Meeting", "Opportunity CIC Approval"] },
  { key: "GREY",   label: "GREY Gate",   description: "Preliminary Design Review / CIC Clearance",                       color: "#6B7280", bgColor: "bg-gray-500",                    reviews: ["Preliminary Design Review", "CIC Clearance"] },
  { key: "GOLD",   label: "GOLD Gate",   description: "Critical Design Review",                                          color: "#EAB308", bgColor: "bg-yellow-500",                  reviews: ["Critical Design Review"] },
  { key: "BLUE",   label: "BLUE Gate",   description: "Commissioning readiness review",                                  color: "#3B82F6", bgColor: "bg-blue-500",                    reviews: ["Commissioning Readiness Review"] },
  { key: "PURPLE", label: "PURPLE Gate", description: "Hand-over to OPS team",                                           color: "#8B5CF6", bgColor: "bg-purple-500",                  reviews: ["Hand-over to OPS Team"] },
  { key: "WHITE",  label: "WHITE Gate",  description: "Final Acceptance Review / Project Closure",                        color: "#F9FAFB", bgColor: "bg-gray-50 border border-gray-300", reviews: ["Final Acceptance Review", "Project Closure"] },
];

/**
 * Canonical lifecycle gate keys in order. Sourced from GATES so the constant
 * never drifts, but typed as a tuple of literal strings so downstream
 * `Record<(typeof GATE_KEYS)[number], …>` mappings stay strictly checked.
 */
export const GATE_KEYS = [
  "RED",
  "AMBER",
  "GREEN",
  "GREY",
  "GOLD",
  "BLUE",
  "PURPLE",
  "WHITE",
] as const satisfies readonly Gate["key"][];
export type GateKey = (typeof GATE_KEYS)[number];

// ─── Engineering Lifecycle (ADEJE) ───────────────────────────────────

const ENGINEERING: LifecycleDefinition = {
  key: "ENGINEERING",
  label: "Engineering",
  defaultPhase: "IDEATION",
  phases: [
    { key: "IDEATION",        phaseNumber: 0, label: "Ideation",             shortLabel: "Ideation",       description: "Exploring the initial idea",        color: "#DC2626", bgColor: "bg-red-600",                        textColor: "text-red-600",   stageGroup: "Pre-Project" },
    { key: "OPPORTUNITY",     phaseNumber: 1, label: "Opportunity",          shortLabel: "Opportunity",    description: "Evaluating business opportunity",   color: "#F97316", bgColor: "bg-orange-500",                     textColor: "text-orange-500", stageGroup: "Project Planning" },
    { key: "FEASIBILITY",     phaseNumber: 2, label: "Feasibility",          shortLabel: "Feasibility",    description: "Assessing technical viability",     color: "#22C55E", bgColor: "bg-green-500",                     textColor: "text-green-500", stageGroup: "Project Planning" },
    { key: "DETAILED_DESIGN", phaseNumber: 3, label: "Detailed Design",      shortLabel: "Detailed Design", description: "Engineering specifications",        color: "#6B7280", bgColor: "bg-gray-500",                      textColor: "text-gray-500",  stageGroup: "Project Execution" },
    { key: "MANUFACTURING",   phaseNumber: 4, label: "Manufacturing",        shortLabel: "Manufacturing",  description: "Producing equipment & materials",   color: "#EAB308", bgColor: "bg-yellow-500",                    textColor: "text-yellow-500", stageGroup: "Project Execution" },
    { key: "INSTALLATION",    phaseNumber: 5, label: "Installation",         shortLabel: "Installation",   description: "On-site deployment",                color: "#14B8A6", bgColor: "bg-teal-500",                      textColor: "text-teal-500",  stageGroup: "Project Execution" },
    { key: "COMMISSIONING",   phaseNumber: 6, label: "Commissioning",        shortLabel: "Commissioning",  description: "Testing & validating the system",   color: "#3B82F6", bgColor: "bg-blue-500",                      textColor: "text-blue-500",  stageGroup: "Project Execution" },
    { key: "RAMP_UP",         phaseNumber: 7, label: "Ramp-up and Closing",  shortLabel: "Ramp-up",        description: "Scaling to full capacity",          color: "#8B5CF6", bgColor: "bg-purple-500",                    textColor: "text-purple-500", stageGroup: "Project Execution" },
    { key: "BENEFITS",        phaseNumber: 8, label: "Benefits Assessment",  shortLabel: "Benefits",       description: "Measuring realised value",          color: "#FFFFFF", bgColor: "bg-white border border-gray-300", textColor: "text-gray-700",  stageGroup: "Post Project" },
    { key: "CLOSED",          phaseNumber: 9, label: "Closed",               shortLabel: "Closed",         description: "Project completed",                 color: "#1F2937", bgColor: "bg-gray-800",                      textColor: "text-gray-800",  stageGroup: "Closed" },
  ],
  phaseGateMap: {
    IDEATION:        ["RED"],
    OPPORTUNITY:     ["AMBER", "GREEN"],
    FEASIBILITY:     ["GREY"],
    DETAILED_DESIGN: ["GOLD"],
    MANUFACTURING:   [],
    INSTALLATION:    ["BLUE"],
    COMMISSIONING:   [],
    RAMP_UP:         ["PURPLE"],
    BENEFITS:        ["WHITE"],
    CLOSED:          [],
  },
  gatePositions: [
    { key: "RED",    at: 1 },
    { key: "AMBER",  at: 1.5 },
    { key: "GREEN",  at: 2 },
    { key: "GREY",   at: 3 },
    { key: "GOLD",   at: 4 },
    { key: "BLUE",   at: 6 },
    { key: "PURPLE", at: 7 },
    { key: "WHITE",  at: 8 },
  ],
};

// ─── IT Lifecycle ────────────────────────────────────────────────────

const IT: LifecycleDefinition = {
  key: "IT",
  label: "IT",
  defaultPhase: "IDEATION",
  phases: [
    { key: "IDEATION",          phaseNumber: 0, label: "Ideation",            shortLabel: "Ideation",     description: "Exploring the initial idea",                  color: "#DC2626", bgColor: "bg-red-600",                        textColor: "text-red-600",    stageGroup: "Pre-Project" },
    { key: "OPPORTUNITY",       phaseNumber: 1, label: "Opportunity",         shortLabel: "Opportunity",  description: "Evaluating business opportunity",             color: "#F97316", bgColor: "bg-orange-500",                     textColor: "text-orange-500", stageGroup: "Project Planning" },
    { key: "FEASIBILITY",       phaseNumber: 2, label: "Feasibility",         shortLabel: "Feasibility",  description: "Assessing technical viability",               color: "#22C55E", bgColor: "bg-green-500",                     textColor: "text-green-500",  stageGroup: "Project Planning" },
    { key: "DESIGN",            phaseNumber: 3, label: "Design",              shortLabel: "Design",       description: "Solution architecture and design",            color: "#6B7280", bgColor: "bg-gray-500",                      textColor: "text-gray-500",   stageGroup: "Project Execution" },
    { key: "REALISATION",       phaseNumber: 4, label: "Realisation",         shortLabel: "Realisation",  description: "Development, integration and testing",        color: "#EAB308", bgColor: "bg-yellow-500",                    textColor: "text-yellow-500", stageGroup: "Project Execution" },
    { key: "DEPLOY",            phaseNumber: 5, label: "Deploy",              shortLabel: "Deploy",       description: "Deploying to production",                     color: "#3B82F6", bgColor: "bg-blue-500",                      textColor: "text-blue-500",   stageGroup: "Project Execution" },
    { key: "HYPERCARE_CLOSING", phaseNumber: 6, label: "Hypercare & Closing", shortLabel: "Hypercare",    description: "Post-go-live support, transition and closure", color: "#8B5CF6", bgColor: "bg-purple-500",                  textColor: "text-purple-500", stageGroup: "Project Execution" },
    { key: "BENEFITS",          phaseNumber: 7, label: "Benefit Assessment",  shortLabel: "Benefits",     description: "Measuring realised value",                    color: "#FFFFFF", bgColor: "bg-white border border-gray-300", textColor: "text-gray-700",   stageGroup: "Post Project" },
    { key: "CLOSED",            phaseNumber: 8, label: "Closed",              shortLabel: "Closed",       description: "Project completed",                           color: "#1F2937", bgColor: "bg-gray-800",                      textColor: "text-gray-800",   stageGroup: "Closed" },
  ],
  phaseGateMap: {
    IDEATION:          ["RED"],
    OPPORTUNITY:       ["AMBER", "GREEN"],
    FEASIBILITY:       ["GREY"],
    DESIGN:            ["GOLD"],
    REALISATION:       ["BLUE"],
    DEPLOY:            [],
    HYPERCARE_CLOSING: ["PURPLE"],
    BENEFITS:          ["WHITE"],
    CLOSED:            [],
  },
  gatePositions: [
    { key: "RED",    at: 1 },
    { key: "AMBER",  at: 1.5 },
    { key: "GREEN",  at: 2 },
    { key: "GREY",   at: 3 },
    { key: "GOLD",   at: 4 },
    { key: "BLUE",   at: 5 },
    { key: "PURPLE", at: 6 },
    { key: "WHITE",  at: 7 },
  ],
};

// ─── Lifecycle Registry ──────────────────────────────────────────────

const LIFECYCLES: Record<string, LifecycleDefinition> = { ENGINEERING, IT };

export const LIFECYCLE_TYPES = Object.values(LIFECYCLES).map(({ key, label }) => ({ key, label }));

/** Get the full lifecycle definition */
export function getLifecycle(lifecycleType?: string | null): LifecycleDefinition {
  return LIFECYCLES[lifecycleType ?? "ENGINEERING"] ?? ENGINEERING;
}

/** Get phases for a given lifecycle type */
export function getPhasesForLifecycle(lifecycleType?: string | null): Phase[] {
  return getLifecycle(lifecycleType).phases;
}

/** Get the default (first) phase key for a lifecycle */
export function getDefaultPhase(lifecycleType?: string | null): string {
  return getLifecycle(lifecycleType).defaultPhase;
}

/** Get phase-gate map for a lifecycle */
export function getPhaseGateMap(lifecycleType?: string | null): Record<string, string[]> {
  return getLifecycle(lifecycleType).phaseGateMap;
}

/** Get gate positions for timeline rendering */
export function getGatePositions(lifecycleType?: string | null): GatePosition[] {
  return getLifecycle(lifecycleType).gatePositions;
}

/** Get the total phase count (for timeline axis) — excludes "Closed" */
export function getVisiblePhaseCount(lifecycleType?: string | null): number {
  return getLifecycle(lifecycleType).phases.filter((p) => p.stageGroup !== "Closed").length;
}

/** Backward compat: default PHASES (Engineering) */
export const PHASES: Phase[] = ENGINEERING.phases;

/** Get execution phase keys for a lifecycle */
export function getExecutionPhases(lifecycleType?: string | null): string[] {
  return getLifecycle(lifecycleType).phases
    .filter((p) => p.stageGroup === "Project Execution")
    .map((p) => p.key);
}

/** Backward compat: Engineering execution phases */
export const EXECUTION_PHASES: string[] = getExecutionPhases("ENGINEERING");

// Tier Definitions
export interface Tier {
  key: string;
  label: string;
  description: string;
}

export const TIERS: Record<string, Tier> = {
  TIER_1: {
    key: "TIER_1",
    label: "Tier 1",
    description: "Strategic, >1M€",
  },
  TIER_2: {
    key: "TIER_2",
    label: "Tier 2",
    description: "Medium impact",
  },
  TIER_3: {
    key: "TIER_3",
    label: "Tier 3",
    description: "Operational",
  },
};

// ─── Project Lifecycle Status (active / on-hold / completed / cancelled) ──

export interface ProjectStatusDef {
  key: string;
  label: string;
  shortLabel: string;
  color: string; // hex — used as the band background
}

export const PROJECT_STATUSES: ProjectStatusDef[] = [
  { key: "ACTIVE",    label: "Active",            shortLabel: "ACTIVE",    color: "#22C55E" },
  { key: "ON_HOLD",   label: "On Hold",           shortLabel: "ON HOLD",   color: "#F59E0B" },
  { key: "COMPLETED", label: "Closed / Complete", shortLabel: "COMPLETED", color: "#3B82F6" },
  { key: "CANCELLED", label: "Cancelled",         shortLabel: "CANCELLED", color: "#EF4444" },
];

export const PROJECT_STATUS_DEFAULT = "ACTIVE";

export function getProjectStatus(key?: string | null): ProjectStatusDef {
  return PROJECT_STATUSES.find((s) => s.key === key) ?? PROJECT_STATUSES[0];
}

// Project surface flags — drive list filters and hero badges.
// Source of truth for labels matches the Prisma ProjectFlag enum keys.
export type ProjectFlagKey = "MSR" | "EXCOM_PRESENTING";

export interface ProjectFlagDef {
  key: ProjectFlagKey;
  label: string;
  hint: string;
}

export const PROJECT_FLAGS: ProjectFlagDef[] = [
  { key: "MSR",              label: "MSR",              hint: "Included in the Monthly Status Report" },
  { key: "EXCOM_PRESENTING", label: "ExCom Presenting", hint: "Currently presenting at the Executive Committee" },
];

// Risk Categories with Colors
export interface RiskCategory {
  key: string;
  label: string;
  color: string;
  bgColor: string;
  textColor: string;
}

export const RISK_CATEGORIES: RiskCategory[] = [
  {
    key: "TECHNICAL",
    label: "Technical",
    color: "#3B82F6",
    bgColor: "bg-blue-100",
    textColor: "text-blue-700",
  },
  {
    key: "SCHEDULE",
    label: "Schedule",
    color: "#F97316",
    bgColor: "bg-orange-100",
    textColor: "text-orange-700",
  },
  {
    key: "BUDGET",
    label: "Budget",
    color: "#EAB308",
    bgColor: "bg-yellow-100",
    textColor: "text-yellow-700",
  },
  {
    key: "RESOURCE",
    label: "Resource",
    color: "#8B5CF6",
    bgColor: "bg-purple-100",
    textColor: "text-purple-700",
  },
  {
    key: "QUALITY",
    label: "Quality",
    color: "#EC4899",
    bgColor: "bg-pink-100",
    textColor: "text-pink-700",
  },
  {
    key: "EXTERNAL",
    label: "External",
    color: "#6B7280",
    bgColor: "bg-gray-100",
    textColor: "text-gray-700",
  },
];

// Risk Impact Levels
export interface RiskImpactLevel {
  key: string;
  label: string;
  level: number;
  color: string;
  bgColor: string;
  textColor: string;
}

export const RISK_IMPACTS: RiskImpactLevel[] = [
  {
    key: "LOW",
    label: "Low",
    level: 1,
    color: "#22C55E",
    bgColor: "bg-green-100",
    textColor: "text-green-700",
  },
  {
    key: "MODERATE",
    label: "Moderate",
    level: 2,
    color: "#F97316",
    bgColor: "bg-orange-100",
    textColor: "text-orange-700",
  },
  {
    key: "HIGH",
    label: "High",
    level: 3,
    color: "#DC2626",
    bgColor: "bg-red-100",
    textColor: "text-red-700",
  },
];

// RAG Status Definitions
export interface RAGStatusDef {
  key: string;
  label: string;
  color: string;
  bgColor: string;
  textColor: string;
}

export const RAG_STATUSES: RAGStatusDef[] = [
  { key: "RED",   label: "Red",   color: "#DC2626", bgColor: "bg-red-500",   textColor: "text-red-500" },
  { key: "AMBER", label: "Amber", color: "#F59E0B", bgColor: "bg-amber-500", textColor: "text-amber-500" },
  { key: "GREEN", label: "Green", color: "#22C55E", bgColor: "bg-green-500", textColor: "text-green-500" },
];

// Scope Change Status Definitions
export const SCOPE_CHANGE_STATUSES = [
  { key: "OPEN",      label: "Open",      bgColor: "bg-blue-100",     textColor: "text-blue-700",     darkBg: "dark:bg-blue-900/30",     darkText: "dark:text-blue-300" },
  { key: "APPROVED",  label: "Approved",  bgColor: "bg-emerald-100",  textColor: "text-emerald-700",  darkBg: "dark:bg-emerald-900/30",  darkText: "dark:text-emerald-300" },
  { key: "ON_HOLD",   label: "On Hold",   bgColor: "bg-amber-100",    textColor: "text-amber-700",    darkBg: "dark:bg-amber-900/30",    darkText: "dark:text-amber-300" },
  { key: "CANCELLED", label: "Cancelled", bgColor: "bg-red-100",      textColor: "text-red-700",      darkBg: "dark:bg-red-900/30",      darkText: "dark:text-red-300" },
];

// Helper Functions

/**
 * Get phase by key
 */
export function getPhaseByKey(key: string, lifecycleType?: string | null): Phase | undefined {
  return getPhasesForLifecycle(lifecycleType).find((phase) => phase.key === key);
}

/**
 * Get gate by key
 */
export function getGateByKey(key: string): Gate | undefined {
  return GATES.find((gate) => gate.key === key);
}

/**
 * Get the next gate(s) for a given phase
 */
export function getNextGateForPhase(phaseKey: string, lifecycleType?: string | null): Gate[] {
  const map = getPhaseGateMap(lifecycleType);
  const gateKeys = map[phaseKey] || [];
  return gateKeys.map((key) => getGateByKey(key)).filter((gate) => gate !== undefined) as Gate[];
}

/**
 * Get phase color in hex format
 */
export function getPhaseColor(phaseKey: string, lifecycleType?: string | null): string {
  const phase = getPhaseByKey(phaseKey, lifecycleType);
  return phase?.color || "#6B7280";
}

/**
 * Get phase background color in Tailwind format
 */
export function getPhaseBgColor(phaseKey: string, lifecycleType?: string | null): string {
  const phase = getPhaseByKey(phaseKey, lifecycleType);
  return phase?.bgColor || "bg-gray-500";
}

/**
 * Get phase text color in Tailwind format
 */
export function getPhaseTextColor(phaseKey: string, lifecycleType?: string | null): string {
  const phase = getPhaseByKey(phaseKey, lifecycleType);
  return phase?.textColor || "text-gray-500";
}

/**
 * Get gate color in hex format
 */
export function getGateColor(gateKey: string): string {
  const gate = getGateByKey(gateKey);
  return gate?.color || "#6B7280";
}

/**
 * Get gate background color in Tailwind format
 */
export function getGateBgColor(gateKey: string): string {
  const gate = getGateByKey(gateKey);
  return gate?.bgColor || "bg-gray-500";
}

/**
 * Get all phases in a stage group
 */
export function getPhasesByStageGroup(stageGroup: string, lifecycleType?: string | null): Phase[] {
  return getPhasesForLifecycle(lifecycleType).filter((phase) => phase.stageGroup === stageGroup);
}

/**
 * Get phase number by key
 */
export function getPhaseNumber(phaseKey: string, lifecycleType?: string | null): number {
  const phase = getPhaseByKey(phaseKey, lifecycleType);
  return phase?.phaseNumber ?? -1;
}

/**
 * Get next phase in sequence
 */
export function getNextPhase(currentPhaseKey: string, lifecycleType?: string | null): Phase | undefined {
  const phases = getPhasesForLifecycle(lifecycleType);
  const currentPhase = phases.find((p) => p.key === currentPhaseKey);
  if (!currentPhase) return undefined;
  return phases.find((phase) => phase.phaseNumber === currentPhase.phaseNumber + 1);
}

/**
 * Get previous phase in sequence
 */
export function getPreviousPhase(currentPhaseKey: string, lifecycleType?: string | null): Phase | undefined {
  const phases = getPhasesForLifecycle(lifecycleType);
  const currentPhase = phases.find((p) => p.key === currentPhaseKey);
  if (!currentPhase) return undefined;
  return phases.find((phase) => phase.phaseNumber === currentPhase.phaseNumber - 1);
}

/**
 * Get risk category by key
 */
export function getRiskCategoryByKey(key: string): RiskCategory | undefined {
  return RISK_CATEGORIES.find((cat) => cat.key === key);
}

/**
 * Get risk impact by key
 */
export function getRiskImpactByKey(key: string): RiskImpactLevel | undefined {
  return RISK_IMPACTS.find((imp) => imp.key === key);
}

/**
 * Get tier by key
 */
export function getTierByKey(key: string): Tier | undefined {
  return TIERS[key];
}

/**
 * Check if phase is in execution stage
 */
export function isExecutionPhase(phaseKey: string, lifecycleType?: string | null): boolean {
  const phase = getPhaseByKey(phaseKey, lifecycleType);
  return phase?.stageGroup === "Project Execution";
}

/**
 * Check if project is complete (last two stages are always Post Project + Closed)
 */
export function isProjectComplete(phaseKey: string, lifecycleType?: string | null): boolean {
  const phase = getPhaseByKey(phaseKey, lifecycleType);
  return phase?.stageGroup === "Post Project" || phase?.stageGroup === "Closed";
}
