"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { UserSelector, type SelectedUser } from "@/components/ui/user-selector";
import { PropLabel } from "@/components/ui/auto-fields";
import { ListSelector } from "@/components/ui/list-selector";
import { PhaseSelector } from "@/components/ui/phase-selector";
import { FlagPicker } from "@/components/ui/flag-picker";
import { Switch } from "@/components/ui/switch";
import { TIERS, LIFECYCLE_TYPES, getDefaultPhase, type ProjectFlagKey } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { useReferenceData } from "@/hooks/use-reference-data";
import { CountryFlag } from "@/components/ui/country-flag";

interface ProjectFormData {
  reference: string;
  name: string;
  tier: string;
  lifecycleType: string;
  categoryId: string;
  factoryId: string;
  currentPhase: string;
  plannedCompletionDate: string;
  description: string;
  objective: string;
  flags: ProjectFlagKey[];
  isConfidential: boolean;
}

const EMPTY_FORM: ProjectFormData = {
  reference: "",
  name: "",
  tier: "TIER_1",
  lifecycleType: "ENGINEERING",
  categoryId: "",
  factoryId: "",
  currentPhase: "IDEATION",
  plannedCompletionDate: "",
  description: "",
  objective: "",
  flags: [],
  isConfidential: false,
};

/* ── Validation ───────────────────────────────────────────────────── */

type TouchedFields = Record<string, boolean>;

function fieldError(field: string, formData: ProjectFormData, touched: TouchedFields, submitted: boolean): boolean {
  if (!touched[field] && !submitted) return false;
  switch (field) {
    case "name": return !formData.name.trim();
    case "factoryId": return !formData.factoryId;
    default: return false;
  }
}

const INPUT_ERROR = "!border-red-400 focus:!ring-red-400/20";
const SELECT_ERROR = "[&>button]:!border-red-400 [&>button]:focus:!ring-red-400/20";

/* ── Component ─────────────────────────────────────────────────────── */

interface ProjectFormProps {
  mode: "create";
  onSuccess?: (project: { id: string }) => void;
  onCancel: () => void;
}

export function ProjectForm({ onSuccess, onCancel }: ProjectFormProps) {
  const { factories, categories } = useReferenceData();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [touched, setTouched] = useState<TouchedFields>({});

  const [formData, setFormData] = useState<ProjectFormData>(EMPTY_FORM);
  const [sponsors, setSponsors] = useState<SelectedUser[]>([]);
  const [owners, setOwners] = useState<SelectedUser[]>([]);
  const [pms, setPms] = useState<SelectedUser[]>([]);
  const [pmos, setPmos] = useState<SelectedUser[]>([]);

  const touch = (field: string) =>
    setTouched((t) => (t[field] ? t : { ...t, [field]: true }));

  const err = (field: string) => fieldError(field, formData, touched, submitted);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitted(true);

    const hasErrors =
      !formData.name.trim() ||
      !formData.factoryId;

    if (hasErrors) {
      setError("Please fill in all required fields");
      return;
    }

    setSaving(true);
    setError("");

    try {
      const assignments = [
        ...sponsors.map((u) => ({ userId: u.id, role: "SPONSOR" })),
        ...owners.map((u) => ({ userId: u.id, role: "OWNER" })),
        ...pms.map((u) => ({ userId: u.id, role: "PROJECT_MANAGER" })),
        ...pmos.map((u) => ({ userId: u.id, role: "PMO" })),
      ];

      const body = {
        ...formData,
        categoryId: formData.categoryId || null,
        factoryId: formData.factoryId || null,
        plannedCompletionDate: formData.plannedCompletionDate || null,
        flags: formData.flags,
        assignments,
      };

      const res = await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "Failed to create project");
      }

      const project = await res.json();
      onSuccess?.(project);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create project");
    } finally {
      setSaving(false);
    }
  };

  const set = (key: keyof ProjectFormData, value: string) =>
    setFormData((p) => {
      const next = { ...p, [key]: value };
      // When lifecycle changes, reset phase to the new lifecycle's default
      if (key === "lifecycleType" && value !== p.lifecycleType) {
        next.currentPhase = getDefaultPhase(value);
      }
      return next;
    });

  return (
    <form onSubmit={handleSubmit} className="space-y-6" noValidate>
      {/* ── Project title row: Name + Reference ── */}
      <div className="flex gap-5">
        <div className="flex-1 min-w-0">
          <PropLabel hint="Descriptive name of the project" error={err("name")}>Name *</PropLabel>
          <Input
            placeholder="Untitled project"
            value={formData.name}
            onChange={(e) => set("name", e.target.value)}
            onBlur={() => touch("name")}
            className={cn("font-bold text-etex-charcoal text-base h-10", err("name") && INPUT_ERROR)}
          />
        </div>
        <div className="w-[20%] shrink-0">
          <PropLabel hint="Project code from the Etex Engineering Timesheet. Optional.">Reference</PropLabel>
          <Input
            placeholder="e.g., CCNG"
            value={formData.reference}
            onChange={(e) => set("reference", e.target.value)}
            className="font-mono font-bold text-etex-orange text-base h-10"
          />
        </div>
      </div>

      {/* ── Project metadata ── */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-[120px_140px_minmax(140px,auto)_minmax(120px,auto)_130px_140px] gap-x-5 gap-y-3">
        <div>
          <PropLabel hint="Tier 1 = strategic, Tier 2 = significant, Tier 3 = standard">Tier</PropLabel>
          <Select value={formData.tier} onValueChange={(v) => set("tier", v)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {Object.values(TIERS).map((t) => (
                <SelectItem key={t.key} value={t.key}>{t.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <PropLabel hint="Project lifecycle methodology — determines phase naming">Lifecycle</PropLabel>
          <Select value={formData.lifecycleType} onValueChange={(v) => set("lifecycleType", v)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {LIFECYCLE_TYPES.map((lt) => (
                <SelectItem key={lt.key} value={lt.key}>{lt.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <PropLabel hint="Manufacturing site or business unit this project belongs to" error={err("factoryId")}>Factory *</PropLabel>
          <div className={cn(err("factoryId") && SELECT_ERROR)}>
            <ListSelector
              options={[...factories]
                .sort((a, b) => (b.code ?? "").localeCompare(a.code ?? ""))
                .map((f) => ({
                  value: f.id,
                  label: [f.code, f.name].filter(Boolean).join(" "),
                  searchText: [f.code, f.name, f.country].filter(Boolean).join(" "),
                  data: f,
                }))}
              value={formData.factoryId || undefined}
              onValueChange={(v) => { set("factoryId", v === "__all__" ? "" : v); touch("factoryId"); }}
              allowAll
              placeholder="Select..."
              searchThreshold={0}
              renderOption={(o) => (
                <span className="inline-flex items-center gap-1.5 text-xs font-medium truncate">
                  <CountryFlag code={o.data?.country} />
                  {o.data?.code && <span className="font-bold">{o.data.code}</span>}
                  <span className="truncate">{o.data?.name}</span>
                </span>
              )}
              renderSelected={(o) => (
                <>
                  <CountryFlag code={o.data?.country} />
                  {o.data?.code && <span className="font-bold">{o.data.code}</span>}
                  <span className="truncate">{o.data?.name}</span>
                </>
              )}
            />
          </div>
        </div>
        <div>
          <PropLabel hint="Optional grouping to classify projects by type or domain">Category</PropLabel>
          <ListSelector
            options={[...categories].sort((a, b) => a.code.localeCompare(b.code)).map((c) => ({
              value: c.id,
              label: `${c.code} ${c.name}`,
              searchText: `${c.code} ${c.name}`,
            }))}
            value={formData.categoryId || undefined}
            onValueChange={(v) => set("categoryId", v === "__all__" ? "" : v)}
            allowAll
            placeholder="Select..."
            searchThreshold={0}
            renderOption={(o) => {
              const [code, ...rest] = o.label.split(" ");
              return (
                <span className="inline-flex items-center gap-1.5 text-xs font-medium truncate">
                  <span className="font-bold">{code}</span>
                  <span className="truncate">{rest.join(" ")}</span>
                </span>
              );
            }}
            renderSelected={(o) => {
              const [code, ...rest] = o.label.split(" ");
              return (
                <>
                  <span className="font-bold">{code}</span>
                  <span className="truncate">{rest.join(" ")}</span>
                </>
              );
            }}
          />
        </div>
        <div>
          <PropLabel hint="Toggle MSR (Monthly Status Report) and ExCom Presenting visibility flags">Flags</PropLabel>
          <FlagPicker
            value={formData.flags}
            onChange={(next) => setFormData((p) => ({ ...p, flags: next }))}
          />
        </div>
        <div>
          <PropLabel hint="Restrict visibility to the Project Sponsor, Owner, Manager, PMO, and Administrators only">
            Confidential
          </PropLabel>
          <div className="flex items-center gap-2 h-9">
            <Switch
              checked={formData.isConfidential}
              onCheckedChange={(v) => setFormData((p) => ({ ...p, isConfidential: v }))}
            />
            <span className="text-xs text-etex-gray-600 dark:text-gray-400">
              {formData.isConfidential ? "Confidential" : "Not confidential"}
            </span>
          </div>
        </div>
      </div>

      {/* ── Additional fields (phase, planned date) ── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-5 gap-y-3">
        <div>
          <PropLabel hint="Current lifecycle stage from Ideation through Benefits realisation">Starting Phase</PropLabel>
          <PhaseSelector
            value={formData.currentPhase}
            onValueChange={(v) => set("currentPhase", v)}
            lifecycleType={formData.lifecycleType}
          />
        </div>
        <div>
          <PropLabel hint="Target date for delivery as approved in the business case">Planned Completion</PropLabel>
          <Input
            type="date"
            value={formData.plannedCompletionDate}
            onChange={(e) => set("plannedCompletionDate", e.target.value)}
          />
        </div>
      </div>

      {/* ── People — matches ProjectDetail grid ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-5 gap-y-3">
        <div>
          <PropLabel hint="Senior leader(s) who champion and fund the project">Sponsor(s)</PropLabel>
          <UserSelector mode="multi" value={sponsors} onChange={setSponsors} placeholder="Select..." />
        </div>
        <div>
          <PropLabel hint="Business stakeholder(s) accountable for project outcomes">Owner(s)</PropLabel>
          <UserSelector mode="multi" value={owners} onChange={setOwners} placeholder="Select..." />
        </div>
        <div>
          <PropLabel hint="Person(s) responsible for day-to-day project execution">Project Manager(s)</PropLabel>
          <UserSelector mode="multi" value={pms} onChange={setPms} placeholder="Select..." requireEmail />
        </div>
        <div>
          <PropLabel hint="PMO contact(s) providing governance and reporting oversight">PMO(s)</PropLabel>
          <UserSelector mode="multi" value={pmos} onChange={setPmos} placeholder="Select..." requireEmail />
        </div>
      </div>

      {/* ── Description & Objective ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-5 gap-y-3">
        <div>
          <PropLabel hint="Brief summary of what this project entails">Description</PropLabel>
          <Textarea
            placeholder="What is this project about…"
            value={formData.description}
            onChange={(e) => set("description", e.target.value)}
            className="min-h-25 resize-none"
          />
        </div>
        <div>
          <PropLabel hint="Measurable outcome or goal this project aims to deliver">Objective</PropLabel>
          <Textarea
            placeholder="What should this project achieve…"
            value={formData.objective}
            onChange={(e) => set("objective", e.target.value)}
            className="min-h-25 resize-none"
          />
        </div>
      </div>

      {/* ── Error & Actions ── */}
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-sm">
          <p className="text-xs text-red-700">{error}</p>
        </div>
      )}

      <div className="flex items-center gap-3 pt-2">
        <Button
          type="submit"
          disabled={saving}
          className="bg-etex-orange hover:bg-orange-700 text-white text-sm px-5"
        >
          {saving ? "Creating…" : "Create Project"}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel} className="text-sm text-gray-500">
          Cancel
        </Button>
      </div>
    </form>
  );
}
