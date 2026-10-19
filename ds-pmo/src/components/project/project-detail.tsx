"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { type SelectedUser } from "@/components/ui/user-selector";
import { AutoTextarea, Section, PropLabel, RowLabel, AutoMetric } from "@/components/ui/auto-fields";
import { RichTextEditor } from "./rich-achievements";
import { ProgressWheel } from "./progress-wheel";
import { SaveIndicator } from "./save-indicator";
import { ProjectHero } from "./sections/project-hero";
import { ProjectMetadata } from "./sections/project-metadata";
import { ProjectPeople } from "./sections/project-people";
import { ProjectSchedule } from "./sections/project-schedule";
import { BudgetTab } from "./tabs/budget-tab";
import { BudgetBreakdownTab } from "./tabs/budget-breakdown-tab";
import { RisksTab } from "./tabs/risks-tab";
import { ScopeChangesTab } from "./tabs/scope-changes-tab";
import { DocumentsTab } from "./tabs/documents-tab";
import { RiacImportDialog } from "./riac-import-dialog";
import { RagWithLabel } from "@/components/ui/rag-with-label";
import { PlannedActionsTab } from "./tabs/planned-actions-tab";
import { PhaseSelector } from "@/components/ui/phase-selector";
import { ReadOnlyProvider } from "@/components/ui/read-only-context";
import { useIsAdmin } from "@/components/layout/session-context";
import { SectionErrorBoundary } from "@/components/ui/section-error-boundary";
import { ProjectLoading, PageError } from "@/components/ui/page-state";
import { GATE_KEYS, getPhaseByKey } from "@/lib/constants";
import { computeProgress } from "@/lib/progress";
import { toSelectedUser } from "@/lib/utils";
import { calcEAC } from "@/lib/calculations";
import type { ProjectWithRelations } from "@/types";
import { api } from "@/lib/api";
import { useReferenceData } from "@/hooks/use-reference-data";
import { SaveStatusContext, SAVE_DEBOUNCE_MS, type SaveStatus, type SaveActions } from "@/hooks/use-save-status";
import { useRouter } from "next/navigation";
import { toast, reportApiError } from "@/lib/toast";

/* ═══════════════════════════════════════════════════════════════════════
   ProjectDetail — orchestrator component
   ═══════════════════════════════════════════════════════════════════════ */

export function ProjectDetail({ projectId }: { projectId: string }) {
  const router = useRouter();
  const [project, setProject] = useState<ProjectWithRelations | null>(null);
  const { factories, categories } = useReferenceData();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [hoveredGate, setHoveredGate] = useState<string | null>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  // Latest snapshot rides along on the project payload (FULL_INCLUDE), so no
  // separate /snapshots fetch is needed for prev-month VAC + buffer display.
  const latestSnapshot = project?.snapshots?.[0] ?? null;

  // ADMIN globalRole always gets edit access, regardless of the server-computed
  // canEdit flag — guards against stale sessions and is the explicit contract.
  const isAdmin = useIsAdmin();
  const canEdit = isAdmin || (project?.canEdit ?? false);

  /* ── Save status callbacks ─────────────────────────────────────── */

  const saving = useCallback(() => {
    clearTimeout(saveTimer.current);
    setSaveStatus("saving");
  }, []);

  const saved = useCallback(() => {
    setSaveStatus("saved");
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => setSaveStatus("idle"), 1500);
  }, []);

  const saveFailed = useCallback(() => {
    setSaveStatus("error");
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => setSaveStatus("idle"), 2500);
  }, []);

  /* ── Ref for stable callbacks ──────────────────────────────────── */

  const projectRef = useRef<ProjectWithRelations | null>(null);
  projectRef.current = project;

  /* ── Data fetching ─────────────────────────────────────────────── */

  const fetchProject = useCallback(async () => {
    try {
      setProject(await api.get<ProjectWithRelations>(`/api/projects/${projectId}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchProject();
  }, [fetchProject]);

  /* ── Debounced batch patch ─────────────────────────────────────── */

  const pendingFields = useRef<Record<string, unknown>>({});
  const patchTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const patchAbort = useRef<AbortController | null>(null);

  const flushPatch = useCallback(async () => {
    const fields = pendingFields.current;
    if (Object.keys(fields).length === 0) return;
    pendingFields.current = {};

    const snapshot: Record<string, unknown> = {};
    const current = projectRef.current;
    if (current) {
      for (const key of Object.keys(fields)) {
        snapshot[key] = (current as unknown as Record<string, unknown>)[key];
      }
    }

    patchAbort.current?.abort();
    const controller = new AbortController();
    patchAbort.current = controller;

    saving();
    try {
      await api.put(`/api/projects/${projectId}`, fields, { signal: controller.signal });
      saved();
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      saveFailed();
      setProject((prev) => (prev ? { ...prev, ...snapshot } : prev));
      // Single toast keyed by "save-failed" — repeated failures replace, not stack.
      void reportApiError(err, "Couldn’t save your changes — your edit was reverted.");
    }
  }, [projectId, saving, saved, saveFailed]);

  const patch = useCallback(
    (fields: Record<string, unknown>) => {
      if (!projectRef.current) return;
      setProject((prev) => (prev ? { ...prev, ...fields } : prev));
      Object.assign(pendingFields.current, fields);
      clearTimeout(patchTimer.current);
      patchTimer.current = setTimeout(flushPatch, SAVE_DEBOUNCE_MS);
    },
    [flushPatch],
  );

  /* ── Patch people (optimistic) ─────────────────────────────────── */

  const peoplePatchAbort = useRef<AbortController | null>(null);

  const patchPeople = useCallback(
    async (
      newAssignments: { userId: string; role: string }[],
      optimistic: Partial<ProjectWithRelations>,
    ) => {
      if (!projectRef.current) return;
      const snapshot = { assignments: projectRef.current.assignments };
      setProject((prev) => (prev ? { ...prev, ...optimistic } : prev));

      // Each of the 4 role selectors (Sponsor/Owner/PM/PMO) fires an
      // immediate, un-debounced PUT of the FULL assignment list on every
      // add/remove. Without cancelling the previous in-flight request, two
      // quick edits (e.g. add a PMO, then add a PM before the first request
      // returns) can resolve out of order — whichever response lands last
      // overwrites state with its own (by-then-stale) assignment snapshot,
      // silently reverting the other edit. Same guard flushPatch uses below.
      peoplePatchAbort.current?.abort();
      const controller = new AbortController();
      peoplePatchAbort.current = controller;

      saving();
      try {
        const updated = await api.put<ProjectWithRelations>(
          `/api/projects/${projectId}`,
          { assignments: newAssignments },
          { signal: controller.signal },
        );
        setProject((prev) => (prev ? { ...prev, assignments: updated.assignments } : prev));
        saved();
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        saveFailed();
        setProject((prev) => (prev ? { ...prev, ...snapshot } : prev));
      }
    },
    [projectId, saving, saved, saveFailed],
  );

  /* ── Delete ────────────────────────────────────────────────────── */

  const handleDelete = useCallback(async () => {
    try {
      await api.delete(`/api/projects/${projectId}`);
      toast.success("Project archived", { description: "It no longer appears in the active list." });
      router.push("/projects");
    } catch (err) {
      saveFailed();
      void reportApiError(err, "Couldn’t archive this project.");
    }
  }, [projectId, router, saveFailed]);

  /* ── Timeline hover (event delegation) ─────────────────────────── */

  const handleTimelineMouseOver = useCallback((e: React.MouseEvent) => {
    let el = e.target as HTMLElement | null;
    while (el && el !== e.currentTarget) {
      if (el.classList.contains("group") && el.classList.contains("absolute")) {
        const spans = el.querySelectorAll("span");
        for (const span of spans) {
          const text = span.textContent?.trim().toUpperCase();
          if (text && (GATE_KEYS as readonly string[]).includes(text)) {
            setHoveredGate(text);
            return;
          }
        }
      }
      el = el.parentElement;
    }
    setHoveredGate(null);
  }, []);

  const handleTimelineMouseLeave = useCallback(() => setHoveredGate(null), []);

  /* ── Memoized values ───────────────────────────────────────────── */

  const saveActions = useMemo<SaveActions>(() => ({ saving, saved, saveFailed }), [saving, saved, saveFailed]);

  const { sponsors, owners, pms, pmos } = useMemo(() => {
    const empty = { sponsors: [] as SelectedUser[], owners: [] as SelectedUser[], pms: [] as SelectedUser[], pmos: [] as SelectedUser[] };
    if (!project) return empty;
    const buckets = { ...empty };
    for (const a of (project.assignments ?? [])) {
      const u = toSelectedUser(a.user);
      if (!u) continue;
      if (a.role === "SPONSOR") buckets.sponsors.push(u);
      else if (a.role === "OWNER") buckets.owners.push(u);
      else if (a.role === "PROJECT_MANAGER") buckets.pms.push(u);
      else if (a.role === "PMO") buckets.pmos.push(u);
    }
    return buckets;
  }, [project]);

  const handleRoleChange = useCallback(
    (changedRole: "SPONSOR" | "OWNER" | "PROJECT_MANAGER" | "PMO", users: SelectedUser[]) => {
      const buckets = { SPONSOR: sponsors, OWNER: owners, PROJECT_MANAGER: pms, PMO: pmos };
      buckets[changedRole] = users;
      const newAssignments = (
        Object.entries(buckets) as [keyof typeof buckets, SelectedUser[]][]
      ).flatMap(([role, list]) => list.map((u) => ({ userId: u.id, role })));
      patchPeople(newAssignments, {
        assignments: newAssignments.map((a) => {
          const u = buckets[a.role].find((s) => s.id === a.userId)!;
          return {
            id: "",
            projectId: project?.id ?? "",
            userId: a.userId,
            role: a.role,
            user: { id: u.id, name: u.name, email: u.email, emailVerified: u.emailVerified },
          } as ProjectWithRelations["assignments"][number];
        }),
      });
    },
    [patchPeople, sponsors, owners, pms, pmos, project?.id],
  );

  const factoryDisplay = useMemo(() => {
    if (!project?.factoryId) return null;
    const f = factories.find((f) => f.id === project.factoryId);
    return f ? { name: f.name, country: f.country, code: f.code } : null;
  }, [project?.factoryId, factories]);

  const categoryDisplay = useMemo(() => {
    if (!project?.categoryId) return null;
    const c = categories.find((c) => c.id === project.categoryId);
    return c ? `${c.code} ${c.name}` : null;
  }, [project?.categoryId, categories]);

  const factoryOptions = useMemo(
    () =>
      [...factories]
        .sort((a, b) => (b.code ?? "").localeCompare(a.code ?? ""))
        .map((f) => ({
          value: f.id,
          label: [f.code, f.name].filter(Boolean).join(" "),
          searchText: [f.code, f.name, f.country].filter(Boolean).join(" "),
          data: f,
        })),
    [factories],
  );

  const categoryOptions = useMemo(
    () =>
      [...categories]
        .sort((a, b) => a.code.localeCompare(b.code))
        .map((c) => ({
          value: c.id,
          label: `${c.code} ${c.name}`,
          searchText: `${c.code} ${c.name}`,
        })),
    [categories],
  );

  const progress = useMemo(() => project ? computeProgress(project.gates ?? []) : 0, [project]);

  /* ── Loading / Error states ────────────────────────────────────── */

  if (loading) return <ProjectLoading />;
  if (error || !project) return <PageError message={error ?? "Project not found"} onRetry={fetchProject} />;

  /* ── Render ────────────────────────────────────────────────────── */

  return (
    <ReadOnlyProvider value={!canEdit}>
      <SaveStatusContext.Provider value={saveActions}>
        <div className="space-y-6">
          {canEdit && <SaveIndicator status={saveStatus} />}

          <ProjectHero
            project={project}
            projectId={projectId}
            patch={patch}
            canEdit={canEdit}
            onDelete={handleDelete}
          />

          <ProjectMetadata
            project={project}
            patch={patch}
            canEdit={canEdit}
            factoryOptions={factoryOptions}
            categoryOptions={categoryOptions}
            factoryDisplay={factoryDisplay}
            categoryDisplay={categoryDisplay}
          />

          <ProjectPeople
            sponsors={sponsors}
            owners={owners}
            pms={pms}
            pmos={pmos}
            canEdit={canEdit}
            onRoleChange={handleRoleChange}
          />

          {/* Objective */}
          <div>
            <PropLabel hint="Measurable outcome or goal this project aims to deliver">Objective</PropLabel>
            <RichTextEditor
              value={project.objective ?? ""}
              placeholder="What should this project achieve…"
              onSave={(v) => patch({ objective: v || null })}
            />
          </div>

          {/* Scope */}
          <SectionErrorBoundary section="Scope">
            <Section
              title="Scope"
              headerExtra={
                <RagWithLabel
                  value={project.ragScope}
                  label={project.ragScopeLabel}
                  onChangeStatus={(v) => patch({ ragScope: v })}
                  onChangeLabel={(v) => patch({ ragScopeLabel: v })}
                  placeholder="e.g. Controlled"
                />
              }
            >
              <div>
                <PropLabel hint="Work packages and deliverables included in this project">In Scope</PropLabel>
                <AutoTextarea
                  value={project.scope ?? ""}
                  placeholder="What is included…"
                  onSave={(v) => patch({ scope: v || null })}
                />
              </div>
              <div className="mt-5">
                <ScopeChangesTab
                  projectId={projectId}
                  scopeChanges={project.scopeChanges ?? []}
                />
              </div>
            </Section>
          </SectionErrorBoundary>

          {/* Overall */}
          <SectionErrorBoundary section="Overall">
            <Section
              title="Overall"
              headerExtra={
                <RagWithLabel
                  value={project.ragProgress}
                  label={project.ragProgressLabel}
                  onChangeStatus={(v) => patch({ ragProgress: v })}
                  onChangeLabel={(v) => patch({ ragProgressLabel: v })}
                  placeholder="e.g. On Track"
                />
              }
            >
              <div className="space-y-4">
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-[minmax(160px,auto)_auto] gap-x-5 gap-y-3">
                  <div>
                    <PropLabel hint="Current lifecycle stage — drives gate reviews and reporting">Phase</PropLabel>
                    <PhaseSelector
                      value={project.currentPhase}
                      onValueChange={(v) => patch({ currentPhase: v })}
                      lifecycleType={project.lifecycleType}
                    />
                  </div>
                  <ProgressWheel
                    value={progress}
                    phase={getPhaseByKey(project.currentPhase, project.lifecycleType)}
                  />
                </div>
                <div>
                  <PropLabel hint="Notable milestones or deliverables completed this reporting period">Key Achievements</PropLabel>
                  <RichTextEditor
                    value={project.keyAchievements ?? ""}
                    placeholder="Key achievements, one per line…"
                    onSave={(v) => patch({ keyAchievements: v || null })}
                  />
                </div>

                <div>
                  <PropLabel hint="Short-form next steps shown on the one-pager">Planned Actions</PropLabel>
                  <PlannedActionsTab projectId={projectId} plannedActions={project.plannedActions ?? []} />
                </div>
              </div>
            </Section>
          </SectionErrorBoundary>

          {/* Time */}
          <SectionErrorBoundary section="Time">
            <Section
              title="Time"
              headerExtra={
                <RagWithLabel
                  value={project.ragSchedule}
                  label={project.ragScheduleLabel}
                  onChangeStatus={(v) => patch({ ragSchedule: v })}
                  onChangeLabel={(v) => patch({ ragScheduleLabel: v })}
                  placeholder="e.g. On Schedule"
                />
              }
            >
              <ProjectSchedule
                project={project}
                projectId={projectId}
                patch={patch}
                latestSnapshot={latestSnapshot}
                hoveredGate={hoveredGate}
                onTimelineMouseOver={handleTimelineMouseOver}
                onTimelineMouseLeave={handleTimelineMouseLeave}
                onGateHover={setHoveredGate}
              />

              {/* Float / Green-White inputs moved into the Schedule Inputs
                  card above so all schedule entries live together. */}
            </Section>
          </SectionErrorBoundary>

          {/* Cost */}
          <SectionErrorBoundary section="Cost">
            <Section
              title="Cost"
              headerExtra={
                <RagWithLabel
                  value={project.ragCost}
                  label={project.ragCostLabel}
                  onChangeStatus={(v) => patch({ ragCost: v })}
                  onChangeLabel={(v) => patch({ ragCostLabel: v })}
                  placeholder="e.g. Under Budget"
                />
              }
            >
              {/* Business Case — card style matches the Inputs / Summary cards
                  below: header bar, divided grid, inline label + input per cell. */}
              <div className="rounded-md border border-border bg-card">
                <div className="px-4 py-2 border-b border-border text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                  Business Case <span className="ml-1 font-normal normal-case tracking-normal text-muted-foreground/70">— set once at project kickoff and updated at gate reviews</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 divide-y sm:divide-y-0 sm:divide-x divide-border">
                  <div className="grid grid-cols-[1fr_140px] items-center gap-3 px-3 py-2">
                    <RowLabel hint="Total project cost (k€)">Total Cost</RowLabel>
                    <AutoMetric value={project.totalCost ?? null} onSave={(v) => patch({ totalCost: v })} unit="k€" />
                  </div>
                  <div className="grid grid-cols-[1fr_140px] items-center gap-3 px-3 py-2">
                    <RowLabel hint="Expected business value (k€)">Expected Value</RowLabel>
                    <AutoMetric value={project.expectedValue ?? null} onSave={(v) => patch({ expectedValue: v })} unit="k€" />
                  </div>
                  <div className="grid grid-cols-[1fr_140px] items-center gap-3 px-3 py-2">
                    <RowLabel hint="Return on investment (%)">ROI</RowLabel>
                    <AutoMetric value={project.roi ?? null} onSave={(v) => patch({ roi: v })} unit="%" />
                  </div>
                  <div className="grid grid-cols-[1fr_140px] items-center gap-3 px-3 py-2">
                    <RowLabel hint="Payback period in years">Payback</RowLabel>
                    <AutoMetric value={project.paybackYears ?? null} onSave={(v) => patch({ paybackYears: v })} unit="yr" />
                  </div>
                </div>
              </div>

              <div className="mt-6 pt-5 border-t border-border">
                <div className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-3">
                  Budget at Completion <span className="ml-1 font-normal normal-case tracking-normal text-muted-foreground/70">— updated each reporting period</span>
                </div>
                <BudgetBreakdownTab
                  projectId={projectId}
                  createdAt={project.createdAt}
                  actualStartDate={project.actualStartDate}
                  plannedCompletionDate={project.plannedCompletionDate}
                  expectedCompletionDate={project.expectedCompletionDate}
                  onBacChanged={(bac) => setProject((prev) => prev ? { ...prev, budget: prev.budget ? { ...prev.budget, bac } : prev.budget } : prev)}
                />
                <div className="mt-6">
                  <BudgetTab
                    projectId={projectId}
                    budget={project.budget}
                    prevMonthVAC={latestSnapshot?.varianceAtCompletion ?? null}
                    prevMonthLabel={latestSnapshot?.periodLabel ?? null}
                  />
                </div>
              </div>
            </Section>
          </SectionErrorBoundary>

          {/* Resources */}
          <SectionErrorBoundary section="Resources">
            <Section
              title="Resources"
              headerExtra={
                <RagWithLabel
                  value={project.ragResources}
                  label={project.ragResourcesLabel}
                  onChangeStatus={(v) => patch({ ragResources: v })}
                  onChangeLabel={(v) => patch({ ragResourcesLabel: v })}
                  placeholder="e.g. Motivation dropping"
                />
              }
            >
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-5 gap-y-3">
                <div>
                  <PropLabel hint="Percentage of allocated team / budget consumed (manual input). Used by the Schedule Performance card on the one-pager.">
                    Resource consumption
                  </PropLabel>
                  <AutoMetric
                    value={project.resourceConsumptionPct ?? null}
                    onSave={(v) => patch({ resourceConsumptionPct: v })}
                    unit="%"
                  />
                </div>
              </div>
            </Section>
          </SectionErrorBoundary>

          {/* Risks */}
          <SectionErrorBoundary section="Risks">
            <Section
              title="Risks"
              headerExtra={
                <RagWithLabel
                  value={project.ragRisk}
                  label={project.ragRiskLabel}
                  onChangeStatus={(v) => patch({ ragRisk: v })}
                  onChangeLabel={(v) => patch({ ragRiskLabel: v })}
                  placeholder="e.g. Critical"
                />
              }
            >
              <RisksTab
                projectId={projectId}
                risks={project.risks ?? []}
                riskSummary={project.riskSummary}
                riskCounts={{
                  risksIssuesCount: project.risksIssuesCount ?? null,
                  risksHighCount: project.risksHighCount ?? null,
                  risksModerateCount: project.risksModerateCount ?? null,
                  risksLowCount: project.risksLowCount ?? null,
                  risksIdentifiedCount: project.risksIdentifiedCount ?? null,
                  risksQuantifiedCount: project.risksQuantifiedCount ?? null,
                  totalCostAtRisk: project.totalCostAtRisk ?? null,
                  totalTimeImpact: project.totalTimeImpact ?? null,
                }}
                eac={project.budget ? calcEAC(project.budget) : 0}
                projectStart={project.actualStartDate ?? project.createdAt}
                plannedCompletionDate={project.plannedCompletionDate}
                onPatchProject={patch}
                toolbar={canEdit ? <RiacImportDialog projectId={projectId} onImported={fetchProject} /> : undefined}
              />
            </Section>
          </SectionErrorBoundary>

          {/* Documents */}
          <SectionErrorBoundary section="Documents">
            <Section title="Documents">
              <DocumentsTab
                projectId={projectId}
                fixedUrls={{
                  scheduleDocUrl: project.scheduleDocUrl,
                  costDocUrl: project.costDocUrl,
                  riacDocUrl: project.riacDocUrl,
                }}
                onPatchProject={patch}
                documents={project.documents ?? []}
              />
            </Section>
          </SectionErrorBoundary>
        </div>
      </SaveStatusContext.Provider>
    </ReadOnlyProvider>
  );
}
