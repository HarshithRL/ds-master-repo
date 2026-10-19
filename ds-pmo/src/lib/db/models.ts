// Plain TS types replacing what used to come from `@/generated/prisma`
// (the Prisma-generated client). Field names/types mirror prisma/schema.prisma
// exactly — camelCase, `Date` for TIMESTAMP, `| null` for nullable columns —
// so every existing consumer (API routes, components) needs only an import-path
// change, not a shape change.

// ─── Enums ──────────────────────────────────────────────────────────────

export type GlobalRole = "ADMIN" | "EXECUTIVE" | "MEMBER";
export type Permission = "MANAGE_USERS" | "MANAGE_FACTORIES" | "MANAGE_CATEGORIES" | "MANAGE_DIVISIONS" | "VIEW_AUDIT_LOGS" | "MANAGE_RESOURCES";
export type ProjectStatus = "ACTIVE" | "ON_HOLD" | "COMPLETED" | "CANCELLED";
export type ProjectTier = "TIER_1" | "TIER_2" | "TIER_3";
export type LifecycleType = "ENGINEERING" | "IT";
export type GateType = "RED" | "AMBER" | "GREEN" | "GREY" | "GOLD" | "BLUE" | "PURPLE" | "WHITE";
export type ProjectFlag = "MSR" | "EXCOM_PRESENTING";
export type AssignmentRole = "SPONSOR" | "OWNER" | "PROJECT_MANAGER" | "PMO";
export type GateStatus = "PLANNED" | "IN_REVIEW" | "PASSED" | "DEFERRED";
export type BudgetLineType = "CAPEX" | "OPEX";
export type RiskImpact = "LOW" | "MODERATE" | "HIGH" | "VERY_HIGH";
export type RiskType = "RISK" | "ISSUE";
export type RiskStatus = "OPEN" | "MITIGATING" | "CLOSED" | "ACCEPTED";
export type PlannedActionStatus = "OPEN" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED";
export type ScopeChangeStatus = "OPEN" | "APPROVED" | "ON_HOLD" | "CANCELLED";
export type RAGStatus = "RED" | "AMBER" | "GREEN";

// ─── Entities ───────────────────────────────────────────────────────────

export interface User {
  id: string;
  email: string | null;
  name: string;
  image: string | null;
  globalRole: GlobalRole;
  permissions: Permission[];
  isActive: boolean;
  emailVerified: Date | null;
  lastLoginAt: Date | null;
  createdAt: Date;
  updatedAt: Date;
}

export interface Division {
  id: string;
  name: string;
  isActive: boolean;
  createdAt: Date;
  updatedAt: Date;
}

export interface Factory {
  id: string;
  code: string | null;
  name: string;
  shortName: string | null;
  country: string | null;
  currency: string | null;
  divisionId: string | null;
  isActive: boolean;
  createdAt: Date;
  updatedAt: Date;
}

export interface Category {
  id: string;
  code: string;
  name: string;
  isActive: boolean;
  createdAt: Date;
  updatedAt: Date;
}

/** Governance/Resources page document — admin-editable link library. */
export interface Resource {
  id: string;
  category: string;
  title: string;
  description: string | null;
  href: string;
  format: string | null;
  /** Ascending display order within its category (lower = earlier). */
  sortOrder: number;
  createdAt: Date;
  updatedAt: Date;
}

export interface Project {
  id: string;
  reference: string | null;
  name: string;
  description: string | null;
  objective: string | null;
  scope: string | null;
  scopeExclusions: string | null;
  status: ProjectStatus;
  tier: ProjectTier;
  lifecycleType: LifecycleType;
  categoryId: string | null;
  factoryId: string | null;
  wbsCodes: string[];
  currentPhase: string;
  currentGate: GateType | null;
  keyAchievements: string | null;
  actualStartDate: Date | null;
  plannedCompletionDate: Date | null;
  expectedCompletionDate: Date | null;
  ridsOpen: number | null;
  redFlagsOpen: number | null;
  ragProgress: RAGStatus | null;
  ragSchedule: RAGStatus | null;
  ragCost: RAGStatus | null;
  ragRisk: RAGStatus | null;
  ragScope: RAGStatus | null;
  ragResources: RAGStatus | null;
  ragProgressLabel: string | null;
  ragScheduleLabel: string | null;
  ragCostLabel: string | null;
  ragRiskLabel: string | null;
  ragScopeLabel: string | null;
  ragResourcesLabel: string | null;
  totalFloatExclBuffer: number | null;
  totalFloatInclBuffer: number | null;
  resourceConsumptionPct: number | null;
  totalCost: number | null;
  expectedValue: number | null;
  roi: number | null;
  paybackYears: number | null;
  risksIssuesCount: number | null;
  risksHighCount: number | null;
  risksModerateCount: number | null;
  risksLowCount: number | null;
  risksIdentifiedCount: number | null;
  risksQuantifiedCount: number | null;
  totalCostAtRisk: number | null;
  totalTimeImpact: number | null;
  scheduleDocUrl: string | null;
  costDocUrl: string | null;
  riacDocUrl: string | null;
  isActive: boolean;
  flags: ProjectFlag[];
  /** Visible only to ADMIN and PROJECT_MANAGER/SPONSOR/PMO assigned to this project. */
  isConfidential: boolean;
  createdAt: Date;
  updatedAt: Date;
  lastUpdatedById: string | null;
}

export interface ProjectAssignment {
  id: string;
  projectId: string;
  userId: string;
  role: AssignmentRole;
  createdAt: Date;
}

export interface ScopeGrant {
  id: string;
  userId: string;
  divisionId: string | null;
  factoryId: string | null;
  createdAt: Date;
}

export interface Budget {
  id: string;
  projectId: string;
  bac: number;
  actuals: number;
  committed: number;
  expected: number;
  riskContingencyBudgeted: number;
  riskContingencyConsumed: number;
  mgmtContingencyBudgeted: number;
  mgmtContingencyConsumed: number;
  createdAt: Date;
  updatedAt: Date;
}

export interface BudgetLine {
  id: string;
  budgetId: string;
  type: BudgetLineType;
  year: number;
  amount: number;
}

export interface GateRecord {
  id: string;
  projectId: string;
  gate: GateType;
  status: GateStatus;
  plannedDate: Date | null;
  completedDate: Date | null;
  notes: string | null;
  updatedById: string | null;
  createdAt: Date;
  updatedAt: Date;
}

export interface Risk {
  id: string;
  projectId: string;
  riskNumber: number | null;
  type: RiskType;
  riskStatement: string;
  ifClause: string | null;
  dueToClause: string | null;
  thenClause: string | null;
  impact: RiskImpact;
  category: string | null;
  probability: number | null;
  costImpact: number | null;
  timeImpact: number | null;
  weight: number | null;
  counterMeasures: string | null;
  responseStrategy: string | null;
  completionDate: Date | null;
  ownerName: string | null;
  status: RiskStatus;
  comments: string | null;
  createdAt: Date;
  updatedAt: Date;
}

export interface Milestone {
  id: string;
  projectId: string;
  name: string;
  targetDate: Date | null;
  expectedDate: Date | null;
  remarks: string | null;
  sortOrder: number;
  createdAt: Date;
  updatedAt: Date;
}

export interface PlannedAction {
  id: string;
  projectId: string;
  action: string;
  ownerLabel: string | null;
  byDate: Date | null;
  status: PlannedActionStatus;
  notes: string | null;
  sortOrder: number;
  createdAt: Date;
  updatedAt: Date;
}

export interface ScopeChange {
  id: string;
  projectId: string;
  submittedDate: Date | null;
  description: string;
  impactCost: string | null;
  impactSchedule: string | null;
  impactCostValue: number | null;
  impactScheduleValue: number | null;
  status: ScopeChangeStatus;
  createdAt: Date;
  updatedAt: Date;
}

export interface ProjectDocument {
  id: string;
  projectId: string;
  name: string;
  url: string;
  sortOrder: number;
  createdAt: Date;
  updatedAt: Date;
}

export interface ProjectSnapshot {
  id: string;
  projectId: string;
  projectReference: string;
  projectName: string;
  periodLabel: string;
  notes: string | null;
  createdById: string | null;
  createdAt: Date;
  currentPhase: string | null;
  progress: number | null;
  currentBAC: number | null;
  eac: number | null;
  actualCost: number | null;
  committed: number | null;
  riskContingencyBudgeted: number | null;
  riskContingencyConsumed: number | null;
  mgmtContingencyBudgeted: number | null;
  mgmtContingencyConsumed: number | null;
  varianceAtCompletion: number | null;
  scheduleBuffer: number | null;
  ragProgress: RAGStatus | null;
  ragSchedule: RAGStatus | null;
  ragCost: RAGStatus | null;
  ragRisk: RAGStatus | null;
  ragScope: RAGStatus | null;
  ragResources: RAGStatus | null;
  ragProgressLabel: string | null;
  ragScheduleLabel: string | null;
  ragCostLabel: string | null;
  ragRiskLabel: string | null;
  ragScopeLabel: string | null;
  ragResourcesLabel: string | null;
  ridsOpen: number | null;
  redFlagsOpen: number | null;
  totalFloatExclBuffer: number | null;
  totalFloatInclBuffer: number | null;
  resourceConsumptionPct: number | null;
  openRiskCount: number | null;
  openIssueCount: number | null;
  totalCostAtRisk: number | null;
  totalTimeImpact: number | null;
  plannedCompletionDate: Date | null;
  expectedCompletionDate: Date | null;
}

export interface AuditLog {
  id: string;
  userId: string | null;
  projectId: string | null;
  action: string;
  entity: string;
  entityId: string | null;
  changes: Record<string, { old: unknown; new: unknown }> | null;
  createdAt: Date;
}
