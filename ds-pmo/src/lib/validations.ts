import { z } from "zod";

// ─── Shared Enums ─────────────────────────────────────────────────

// Phase is a free string — validated against the lifecycle's valid phase keys at the API layer
export const PhaseEnum = z.string().min(1);

export const GateEnum = z.enum([
  "RED",
  "AMBER",
  "GREEN",
  "GREY",
  "GOLD",
  "BLUE",
  "PURPLE",
  "WHITE",
]);

export const GateStatusEnum = z.enum([
  "PLANNED",
  "IN_REVIEW",
  "PASSED",
  "DEFERRED",
]);

export const TierEnum = z.enum(["TIER_1", "TIER_2", "TIER_3"]);

export const LifecycleTypeEnum = z.enum(["ENGINEERING", "IT"]);

export const RiskImpactEnum = z.enum([
  "LOW",
  "MODERATE",
  "HIGH",
  "VERY_HIGH",
]);

export const RiskTypeEnum = z.enum(["RISK", "ISSUE"]);

export const RiskStatusEnum = z.enum([
  "OPEN",
  "MITIGATING",
  "CLOSED",
  "ACCEPTED",
]);

export const PermissionEnum = z.enum([
  "MANAGE_USERS",
  "MANAGE_FACTORIES",
  "MANAGE_CATEGORIES",
  "MANAGE_DIVISIONS",
  "VIEW_AUDIT_LOGS",
  "MANAGE_RESOURCES",
]);

export const AssignmentRoleEnum = z.enum(["SPONSOR", "OWNER", "PROJECT_MANAGER", "PMO"]);

export const GlobalRoleEnum = z.enum(["ADMIN", "EXECUTIVE", "MEMBER"]);

// One row = one Division grant OR one Factory grant (XOR).
export const ScopeGrantInput = z
  .object({
    divisionId: z.string().min(1).optional().nullable(),
    factoryId: z.string().min(1).optional().nullable(),
  })
  .refine(
    (g) => Boolean(g.divisionId) !== Boolean(g.factoryId),
    "Scope grant must reference exactly one of divisionId or factoryId",
  );

export const ScopeChangeStatusEnum = z.enum(["OPEN", "APPROVED", "ON_HOLD", "CANCELLED"]);

export const RAGStatusEnum = z.enum(["RED", "AMBER", "GREEN"]);

export const ProjectStatusEnum = z.enum(["ACTIVE", "ON_HOLD", "COMPLETED", "CANCELLED"]);

export const ProjectFlagEnum = z.enum(["MSR", "EXCOM_PRESENTING"]);
export type ProjectFlag = z.infer<typeof ProjectFlagEnum>;

// ─── Reusable field helpers ────────��──────────────────────────────

const cuid = z.string().min(1, "ID is required");
const optionalCuid = z.string().min(1).optional().nullable();
const optionalDateStr = z.string().optional().nullable();
const requiredStr = z.string().min(1, "This field is required").trim();

// project.reference has no real value when blank — fold empty/whitespace to
// null instead of storing "" (a meaningless value distinct from "no
// reference"), and trim real values. Ported from the upstream fix for a
// UNIQUE-index collision on blank references under Postgres; that specific
// failure mode doesn't apply now (Delta has no unique constraints), but
// null-for-"no reference" is still the correct representation either way.
const optionalReference = z
  .string()
  .trim()
  .transform((v) => (v === "" ? null : v))
  .optional()
  .nullable();

// Allow empty (cleared link) but reject anything other than http(s).
// Used for any field that flows into an <a href> sink — `javascript:`,
// `data:`, `vbscript:`, `file:` URIs would otherwise be stored-XSS payloads.
const httpUrlOrEmpty = z
  .string()
  .refine(
    (v) => v === "" || /^https?:\/\//i.test(v),
    "URL must start with http:// or https://",
  );
const httpUrlOrNullable = httpUrlOrEmpty.optional().nullable();

// ─── Admin: Categories ───────────────���────────────────────────────

export const createCategorySchema = z.object({
  name: requiredStr,
  code: requiredStr,
});
export type CreateCategoryInput = z.infer<typeof createCategorySchema>;

export const updateCategorySchema = z.object({
  name: z.string().min(1).trim().optional(),
});
export type UpdateCategoryInput = z.infer<typeof updateCategorySchema>;

// ─── Admin: Resources (Governance page document library) ──────────

const requiredHttpUrl = z
  .string()
  .trim()
  .min(1, "Link is required")
  .refine((v) => /^https?:\/\//i.test(v), "Link must start with http:// or https://");

export const ResourceFormatEnum = z.enum(["PDF", "PPTX", "XLSX", "DOCX", "Link"]);

export const createResourceSchema = z.object({
  category: requiredStr,
  title: requiredStr,
  description: z.string().trim().optional().nullable(),
  href: requiredHttpUrl,
  format: ResourceFormatEnum.optional().nullable(),
});
export type CreateResourceInput = z.infer<typeof createResourceSchema>;

export const updateResourceSchema = z.object({
  category: z.string().min(1).trim().optional(),
  title: z.string().min(1).trim().optional(),
  description: z.string().trim().optional().nullable(),
  href: requiredHttpUrl.optional(),
  format: ResourceFormatEnum.optional().nullable(),
});
export type UpdateResourceInput = z.infer<typeof updateResourceSchema>;

// ─── Admin: Factories ─────────────────────────────────────────────

export const createFactorySchema = z.object({
  name: requiredStr,
  code: z.string().trim().optional().nullable(),
  shortName: z.string().trim().optional().nullable(),
  country: z.string().trim().optional().nullable(),
  currency: z.string().trim().optional().nullable(),
  divisionId: optionalCuid,
});
export type CreateFactoryInput = z.infer<typeof createFactorySchema>;

export const updateFactorySchema = z.object({
  name: z.string().min(1).trim().optional(),
  code: z.string().trim().optional().nullable(),
  shortName: z.string().trim().optional().nullable(),
  country: z.string().trim().optional().nullable(),
  currency: z.string().trim().optional().nullable(),
  divisionId: optionalCuid,
});
export type UpdateFactoryInput = z.infer<typeof updateFactorySchema>;

// ─── Admin: Users ──────────��──────────────────────────────────────

export const createAdminUserSchema = z.object({
  name: requiredStr,
  email: z
    .email()
    .refine((e) => e.endsWith("@etexgroup.com"), "Must be @etexgroup.com")
    .optional()
    .nullable(),
  globalRole: GlobalRoleEnum.default("MEMBER"),
  permissions: z.array(PermissionEnum).default([]),
  scopeGrants: z.array(ScopeGrantInput).default([]),
});
export type CreateAdminUserInput = z.infer<typeof createAdminUserSchema>;

export const updateUserSchema = z.object({
  name: z.string().min(1).trim().optional(),
  globalRole: GlobalRoleEnum.optional(),
  permissions: z.array(PermissionEnum).optional(),
  scopeGrants: z.array(ScopeGrantInput).optional(),
  isActive: z.boolean().optional(),
});
export type UpdateUserInput = z.infer<typeof updateUserSchema>;

// ─── Users (selector / stakeholders) ──────���───────────────────────

export const createUserSchema = z.object({
  name: requiredStr,
  email: z
    .email()
    .refine((e) => e.endsWith("@etexgroup.com"), "Must be @etexgroup.com")
    .optional()
    .nullable(),
});
export type CreateUserInput = z.infer<typeof createUserSchema>;

// ─── Projects ─��───────────────────────────────────────────────────

const assignmentSchema = z.object({
  userId: cuid,
  role: AssignmentRoleEnum,
});

export const createProjectSchema = z.object({
  reference: optionalReference,
  name: requiredStr,
  description: z.string().optional().nullable(),
  objective: z.string().optional().nullable(),
  scope: z.string().optional().nullable(),
  factoryId: optionalCuid,
  categoryId: optionalCuid,
  tier: TierEnum.default("TIER_2"),
  lifecycleType: LifecycleTypeEnum.default("ENGINEERING"),
  status: ProjectStatusEnum.default("ACTIVE"),
  actualStartDate: optionalDateStr,
  plannedCompletionDate: optionalDateStr,
  expectedCompletionDate: optionalDateStr,
  assignments: z.array(assignmentSchema).default([]),
  flags: z.array(ProjectFlagEnum).default([]),
  wbsCodes: z.array(z.string().min(1).max(50)).default([]),
  isConfidential: z.boolean().default(false),
});
export type CreateProjectInput = z.infer<typeof createProjectSchema>;

export const updateProjectSchema = z.object({
  reference: optionalReference,
  name: z.string().optional(),
  description: z.string().optional().nullable(),
  objective: z.string().optional().nullable(),
  scope: z.string().optional().nullable(),
  scopeExclusions: z.string().optional().nullable(),
  factoryId: optionalCuid,
  categoryId: optionalCuid,
  tier: TierEnum.optional(),
  lifecycleType: LifecycleTypeEnum.optional(),
  status: ProjectStatusEnum.optional(),
  actualStartDate: optionalDateStr,
  plannedCompletionDate: optionalDateStr,
  expectedCompletionDate: optionalDateStr,
  currentPhase: PhaseEnum.optional(),
  currentGate: GateEnum.optional().nullable(),
  keyAchievements: z.string().optional().nullable(),
  // Calculated fields are not stored: scheduleBuffer, scheduleBufferPrev,
  // progress, totalFloatInclBufferPrev, and varianceAtCompletion are all
  // derived at the API boundary (see lib/project-derive.ts, lib/calculations.ts).
  isActive: z.boolean().optional(),
  isConfidential: z.boolean().optional(),
  flags: z.array(ProjectFlagEnum).optional(),
  assignments: z.array(assignmentSchema).optional(),
  // RAG indicators (manually set)
  ragProgress: RAGStatusEnum.optional().nullable(),
  ragSchedule: RAGStatusEnum.optional().nullable(),
  ragCost: RAGStatusEnum.optional().nullable(),
  ragRisk: RAGStatusEnum.optional().nullable(),
  ragScope: RAGStatusEnum.optional().nullable(),
  ragResources: RAGStatusEnum.optional().nullable(),
  // Free-text status labels — shown next to each RAG dot on the one-pager
  ragProgressLabel: z.string().max(120).optional().nullable(),
  ragScheduleLabel: z.string().max(120).optional().nullable(),
  ragCostLabel: z.string().max(120).optional().nullable(),
  ragRiskLabel: z.string().max(120).optional().nullable(),
  ragScopeLabel: z.string().max(120).optional().nullable(),
  ragResourcesLabel: z.string().max(120).optional().nullable(),
  // Schedule performance (manual inputs from project details).
  // totalFloatInclBufferPrev and daysGreenToWhite are derived live — see
  // lib/project-derive.ts and lib/progress.ts.
  totalFloatExclBuffer: z.number().int().optional().nullable(),
  totalFloatInclBuffer: z.number().int().optional().nullable(),
  resourceConsumptionPct: z.number().min(0).max(100).optional().nullable(),
  // Business case (one-pager auto-calc)
  totalCost: z.number().optional().nullable(),
  expectedValue: z.number().optional().nullable(),
  roi: z.number().optional().nullable(),
  paybackYears: z.number().optional().nullable(),
  // Schedule maturity KPIs
  ridsOpen: z.number().int().min(0).optional().nullable(),
  redFlagsOpen: z.number().int().min(0).optional().nullable(),
  // Risk summary inputs — editable, autofilled by RIAC import (decoupled from Risk table)
  risksIssuesCount: z.number().int().min(0).optional().nullable(),
  risksHighCount: z.number().int().min(0).optional().nullable(),
  risksModerateCount: z.number().int().min(0).optional().nullable(),
  risksLowCount: z.number().int().min(0).optional().nullable(),
  risksIdentifiedCount: z.number().int().min(0).optional().nullable(),
  risksQuantifiedCount: z.number().int().min(0).optional().nullable(),
  totalCostAtRisk: z.number().min(0).optional().nullable(),
  totalTimeImpact: z.number().int().min(0).optional().nullable(),
  // Document links (fixed) — rendered as <a href>, so restrict to http(s)
  // to block javascript:/data:/vbscript: stored-XSS payloads.
  scheduleDocUrl: httpUrlOrNullable,
  costDocUrl: httpUrlOrNullable,
  riacDocUrl: httpUrlOrNullable,
  // SAP WBS codes
  wbsCodes: z.array(z.string().min(1).max(50)).optional(),
});
export type UpdateProjectInput = z.infer<typeof updateProjectSchema>;

// ─── Budget ───────────────────────────────────────────────────────

export const updateBudgetSchema = z.object({
  actuals: z.number().optional(),
  committed: z.number().optional(),
  expected: z.number().optional(),
  riskContingencyBudgeted: z.number().optional(),
  riskContingencyConsumed: z.number().optional(),
  mgmtContingencyBudgeted: z.number().optional(),
  mgmtContingencyConsumed: z.number().optional(),
});
export type UpdateBudgetInput = z.infer<typeof updateBudgetSchema>;

export const BudgetLineTypeEnum = z.enum(["CAPEX", "OPEX"]);

export const upsertBudgetLineSchema = z.object({
  type: BudgetLineTypeEnum,
  year: z.number().int(),
  amount: z.number(),
});
export type UpsertBudgetLineInput = z.infer<typeof upsertBudgetLineSchema>;

// ─── Gates ───────────────────────────────────────────��────────────

export const updateGateSchema = z.object({
  gate: GateEnum,
  status: GateStatusEnum,
  completedDate: optionalDateStr,
  notes: z.string().optional().nullable(),
  plannedDate: optionalDateStr,
});
export type UpdateGateInput = z.infer<typeof updateGateSchema>;

// ─── Risks ──────────────────────────────────────────��─────────────

export const createRiskSchema = z.object({
  riskStatement: z.string().default(""),
  ifClause: z.string().optional().nullable(),
  dueToClause: z.string().optional().nullable(),
  thenClause: z.string().optional().nullable(),
  type: RiskTypeEnum.default("RISK"),
  impact: RiskImpactEnum.default("MODERATE"),
  probability: z.number().int().min(0).max(100).optional().nullable(),
  costImpact: z.number().optional().nullable(),
  timeImpact: z.number().optional().nullable(),
  counterMeasures: z.string().optional().nullable(),
  ownerName: z.string().optional().nullable(),
});
export type CreateRiskInput = z.infer<typeof createRiskSchema>;

export const updateRiskSchema = z.object({
  riskStatement: z.string().optional(),
  ifClause: z.string().optional().nullable(),
  dueToClause: z.string().optional().nullable(),
  thenClause: z.string().optional().nullable(),
  type: RiskTypeEnum.optional(),
  impact: RiskImpactEnum.optional(),
  category: z.string().optional().nullable(),
  probability: z.number().int().min(0).max(100).optional().nullable(),
  costImpact: z.number().optional().nullable(),
  timeImpact: z.number().optional().nullable(),
  weight: z.number().min(0).optional().nullable(),
  counterMeasures: z.string().optional().nullable(),
  responseStrategy: z.string().optional().nullable(),
  completionDate: optionalDateStr,
  ownerName: z.string().optional().nullable(),
  status: RiskStatusEnum.optional(),
  comments: z.string().optional().nullable(),
});
export type UpdateRiskInput = z.infer<typeof updateRiskSchema>;

// ─── Milestones ─────��─────────────────────────────────────────────

export const createMilestoneSchema = z.object({
  name: z.string().default(""),
  targetDate: optionalDateStr,
  expectedDate: optionalDateStr,
});
export type CreateMilestoneInput = z.infer<typeof createMilestoneSchema>;

export const updateMilestoneSchema = z.object({
  name: z.string().optional(),
  remarks: z.string().optional().nullable(),
  targetDate: optionalDateStr,
  expectedDate: optionalDateStr,
  sortOrder: z.number().int().min(0).optional(),
});
export type UpdateMilestoneInput = z.infer<typeof updateMilestoneSchema>;

export const reorderMilestonesSchema = z.object({
  milestones: z
    .array(z.object({ id: cuid }))
    .min(1, "At least one milestone required"),
});
export type ReorderMilestonesInput = z.infer<typeof reorderMilestonesSchema>;

// ─── Scope Changes ───────────────────────────────────────────────

export const createScopeChangeSchema = z.object({
  description: z.string().default(""),
  submittedDate: z.string().optional().nullable(),
  impactCost: z.string().optional().nullable(),
  impactSchedule: z.string().optional().nullable(),
  impactCostValue: z.number().nullable().optional(),
  impactScheduleValue: z.number().int().nullable().optional(),
  status: ScopeChangeStatusEnum.default("OPEN"),
});
export type CreateScopeChangeInput = z.infer<typeof createScopeChangeSchema>;

export const updateScopeChangeSchema = z.object({
  description: z.string().optional(),
  submittedDate: z.string().optional().nullable(),
  impactCost: z.string().optional().nullable(),
  impactSchedule: z.string().optional().nullable(),
  impactCostValue: z.number().nullable().optional(),
  impactScheduleValue: z.number().int().nullable().optional(),
  status: ScopeChangeStatusEnum.optional(),
});
export type UpdateScopeChangeInput = z.infer<typeof updateScopeChangeSchema>;

// ─── Project Documents ──────────────────────────────────────────

export const createDocumentSchema = z.object({
  name: z.string().default(""),
  url: httpUrlOrEmpty.default(""),
});
export type CreateDocumentInput = z.infer<typeof createDocumentSchema>;

export const updateDocumentSchema = z.object({
  name: z.string().optional(),
  url: httpUrlOrEmpty.optional(),
});
export type UpdateDocumentInput = z.infer<typeof updateDocumentSchema>;

// ─── Snapshots ──────────────────────────────────────────────────

export const createSnapshotSchema = z.object({
  periodLabel: z
    .string()
    .regex(/^\d{4}-\d{2}$/, "Period must be YYYY-MM format")
    .optional(),
  notes: z.string().max(500).optional(),
});
export type CreateSnapshotInput = z.infer<typeof createSnapshotSchema>;

// ─── Planned Actions ─────────────────────────────────────────────

export const PlannedActionStatusEnum = z.enum([
  "OPEN",
  "IN_PROGRESS",
  "COMPLETED",
  "CANCELLED",
]);

export const createPlannedActionSchema = z.object({
  action: z.string().min(1).max(500),
  ownerLabel: z.string().max(120).optional().nullable(),
  byDate: optionalDateStr,
  status: PlannedActionStatusEnum.default("OPEN"),
  notes: z.string().max(1000).optional().nullable(),
  sortOrder: z.number().int().optional(),
});
export type CreatePlannedActionInput = z.infer<typeof createPlannedActionSchema>;

export const updatePlannedActionSchema = z.object({
  action: z.string().min(1).max(500).optional(),
  ownerLabel: z.string().max(120).optional().nullable(),
  byDate: optionalDateStr,
  status: PlannedActionStatusEnum.optional(),
  notes: z.string().max(1000).optional().nullable(),
  sortOrder: z.number().int().optional(),
});
export type UpdatePlannedActionInput = z.infer<typeof updatePlannedActionSchema>;
