import type {
  Project,
  Budget,
  Risk,
  Milestone,
  GateRecord,
  User,
  Factory,
  Division,
  Category,
  ProjectAssignment,
  ScopeChange,
  ProjectDocument,
  AuditLog,
  ProjectSnapshot,
  PlannedAction,
} from "@/lib/db/models";
import type { RiskSummary } from "@/lib/risk-summary";
import type { DerivedProjectFields } from "@/lib/project-derive";
import type { PersistedLifecycleFilter } from "@/lib/lifecycle-filter";

export type { DerivedProjectFields };

// Extended types with relations
export type ProjectWithRelations = Project & DerivedProjectFields & {
  factory: Factory | null;
  category: Category | null;
  lastUpdatedBy: Pick<User, "id" | "name" | "email" | "image"> | null;
  assignments: (ProjectAssignment & { user: User })[];
  budget: Budget | null;
  gates: GateRecord[];
  risks: Risk[];
  milestones: Milestone[];
  scopeChanges: ScopeChange[];
  plannedActions: PlannedAction[];
  documents: ProjectDocument[];
  snapshots: SnapshotDetailItem[];
  riskSummary: RiskSummary;
  canEdit?: boolean;
};

export type FactoryWithDivision = Factory & {
  division: Division | null;
};

export type RiskListItem = Pick<
  Risk,
  "id" | "type" | "impact" | "probability" | "costImpact" | "timeImpact" | "status" | "weight"
>;

export type ScopeChangeListItem = Pick<
  ScopeChange,
  "id" | "status" | "impactCostValue" | "impactScheduleValue"
>;

export type SnapshotListItem = Pick<
  ProjectSnapshot,
  | "periodLabel"
  | "ragProgress"
  | "ragSchedule"
  | "ragCost"
  | "ragRisk"
  | "ragScope"
  | "ragResources"
  | "varianceAtCompletion"
  | "totalFloatInclBuffer"
  | "scheduleBuffer"
>;

/** Subset of ProjectSnapshot returned with the project-detail one-pager. */
export type SnapshotDetailItem = Pick<
  ProjectSnapshot,
  "periodLabel" | "scheduleBuffer" | "totalFloatInclBuffer" | "varianceAtCompletion"
>;

export type ProjectListItem = Project & DerivedProjectFields & {
  factory: FactoryWithDivision | null;
  category: Category | null;
  assignments: (ProjectAssignment & { user: User })[];
  budget: Budget | null;
  gates: GateRecord[];
  risks: RiskListItem[];
  scopeChanges: ScopeChangeListItem[];
  snapshots: SnapshotListItem[];
  riskSummary: RiskSummary;
  _count: {
    risks: number;
  };
};

export type AuditLogWithUser = AuditLog & {
  user: User | null;
  project: Project | null;
};

// Form types
export type ProjectFormData = {
  reference: string;
  name: string;
  description?: string;
  objective?: string;
  scope?: string;
  scopeExclusions?: string;
  tier: "TIER_1" | "TIER_2" | "TIER_3";
  categoryId?: string;
  factoryId?: string;
  currentPhase: string;
  plannedCompletionDate?: string;
  expectedCompletionDate?: string;
};

export type BudgetFormData = {
  actuals: number;
  committed: number;
  expected: number;
  riskContingencyBudgeted: number;
  riskContingencyConsumed: number;
  mgmtContingencyBudgeted: number;
  mgmtContingencyConsumed: number;
};

export type BudgetLineData = {
  type: "CAPEX" | "OPEX";
  year: number;
  amount: number;
};

// Portfolio summary types
export type PortfolioSummary = {
  totalProjects: number;
  totalEAC: number;
  totalBAC: number;
  totalActuals: number;
  totalCommitted: number;
  totalVariance: number;
  avgProgress: number;
  atRiskCount: number;
  overBudgetCount: number;
  inExecutionCount: number;
  onTimeCount: number;
  delayedCount: number;
  byPhase: { phase: string; count: number; eac: number }[];
  byGate: { gate: string; count: number; eac: number }[];
  byTier: { tier: string; count: number; eac: number }[];
  byFactory: { factory: string; count: number; eac: number }[];
  byDivision: { division: string; count: number; eac: number }[];
  riskSummary: { high: number; moderate: number; low: number; issues: number };
};

// Filter options returned by /api/filter-options
export type FilterOptions = {
  divisions: string[];
  factories: { value: string; label: string; division?: string; country?: string }[];
  categories: { value: string; code: string; name: string }[];
  pmos: { id: string; name: string }[];
  pms: { id: string; name: string }[];
  owners: { id: string; name: string }[];
  sponsors: { id: string; name: string }[];
};

// Dashboard filter type
export type DashboardFilters = {
  search?: string;
  /** Omitted means Global (both project lifecycles). */
  lifecycle?: PersistedLifecycleFilter;
  phase?: string[];
  tier?: string[];
  factory?: string[];
  division?: string[];
  category?: string[];
  pmo?: string[];
  pm?: string[];
  owner?: string[];
  sponsor?: string[];
  status?: string[];
  msrOnly?: boolean;
  excomOnly?: boolean;
  sortBy?: string;
  sortDir?: "asc" | "desc";
};

// Snapshot types
export type ProjectSnapshotWithCreator = ProjectSnapshot & {
  createdBy: Pick<User, "id" | "name" | "email"> | null;
};
