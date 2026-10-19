"use client";

import { useEffect, useRef, useState } from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PropLabel } from "@/components/ui/auto-fields";
import { ListSelector } from "@/components/ui/list-selector";
import { CountryFlag } from "@/components/ui/country-flag";
import { FlagPicker } from "@/components/ui/flag-picker";
import { Switch } from "@/components/ui/switch";
import { ProjectStatusBadge } from "@/components/project/project-status-badge";
import {
  TIERS,
  LIFECYCLE_TYPES,
  PROJECT_STATUSES,
  getDefaultPhase,
  type ProjectFlagKey,
} from "@/lib/constants";

import { Plus, X } from "lucide-react";
import type { ProjectWithRelations } from "@/types";

interface ProjectMetadataProps {
  project: ProjectWithRelations;
  patch: (fields: Record<string, unknown>) => void;
  canEdit: boolean;
  factoryOptions: {
    value: string;
    label: string;
    searchText: string;
    data: { name: string; country: string | null; code: string | null };
  }[];
  categoryOptions: { value: string; label: string; searchText: string }[];
  factoryDisplay: { name: string; country: string | null; code: string | null } | null;
  categoryDisplay: string | null;
}

export function ProjectMetadata({ project, patch, canEdit, factoryOptions, categoryOptions, factoryDisplay, categoryDisplay }: ProjectMetadataProps) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-[140px_120px_140px_minmax(160px,auto)_minmax(140px,auto)_160px_minmax(180px,1fr)] gap-x-5 gap-y-3">
      <div>
        <PropLabel hint="Lifecycle state — Active, On Hold, Closed / Complete, or Cancelled.">Status</PropLabel>
        {canEdit ? (
          <Select value={project.status ?? "ACTIVE"} onValueChange={(v) => patch({ status: v })}>
            <SelectTrigger>
              <ProjectStatusBadge status={project.status} />
            </SelectTrigger>
            <SelectContent>
              {PROJECT_STATUSES.map((s) => (
                <SelectItem key={s.key} value={s.key}>
                  <span className="inline-flex items-center gap-2">
                    <span
                      className="inline-block w-2 h-2 rounded-full shrink-0"
                      style={{ backgroundColor: s.color }}
                    />
                    {s.label}
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <div className="form-control-readonly text-sm">
            <ProjectStatusBadge status={project.status} />
          </div>
        )}
      </div>
      <div>
        <PropLabel hint="Tier 1 = strategic, Tier 2 = significant, Tier 3 = standard">Tier</PropLabel>
        {canEdit ? (
          <Select value={project.tier} onValueChange={(v) => patch({ tier: v })}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {Object.values(TIERS).map((t) => (
                <SelectItem key={t.key} value={t.key}>{t.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <div className="form-control-readonly text-sm">
            {TIERS[project.tier as keyof typeof TIERS]?.label ?? project.tier}
          </div>
        )}
      </div>
      <div>
        <PropLabel hint="Project lifecycle methodology — determines phase naming">Lifecycle</PropLabel>
        {canEdit ? (
          <Select value={project.lifecycleType ?? "ENGINEERING"} onValueChange={(v) => patch({ lifecycleType: v, currentPhase: getDefaultPhase(v) })}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {LIFECYCLE_TYPES.map((lt) => (
                <SelectItem key={lt.key} value={lt.key}>{lt.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <div className="form-control-readonly text-sm">
            {LIFECYCLE_TYPES.find((lt) => lt.key === project.lifecycleType)?.label ?? project.lifecycleType}
          </div>
        )}
      </div>
      <div>
        <PropLabel hint="Manufacturing site or business unit this project belongs to">Factory</PropLabel>
        {canEdit ? (
          <ListSelector
            options={factoryOptions}
            value={project.factoryId || undefined}
            onValueChange={(v) => patch({ factoryId: v === "__all__" ? null : v })}
            allowAll
            placeholder="Select…"
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
        ) : (
          <div className="form-control-readonly text-sm">
            {factoryDisplay ? (
              <span className="inline-flex items-center gap-1.5">
                <CountryFlag code={factoryDisplay.country} />
                {factoryDisplay.code && <span className="font-bold">{factoryDisplay.code}</span>}
                {factoryDisplay.name}
              </span>
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </div>
        )}
      </div>
      <div>
        <PropLabel hint="Optional grouping to classify projects by type or domain">Category</PropLabel>
        {canEdit ? (
          <ListSelector
            options={categoryOptions}
            value={project.categoryId || undefined}
            onValueChange={(v) => patch({ categoryId: v === "__all__" ? null : v })}
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
        ) : (
          <div className="form-control-readonly text-sm">
            {categoryDisplay ? (
              <span><span className="font-bold">{categoryDisplay.split(" ")[0]}</span> {categoryDisplay.split(" ").slice(1).join(" ")}</span>
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </div>
        )}
      </div>
      <div>
        <PropLabel hint="Toggle MSR (Monthly Status Report) and ExCom Presenting visibility flags">Flags</PropLabel>
        <FlagPicker
          value={(project.flags ?? []) as ProjectFlagKey[]}
          onChange={(next) => patch({ flags: next })}
          disabled={!canEdit}
        />
      </div>
      <div>
        <PropLabel hint="Restrict visibility to the Project Manager, Sponsor, PMO, and Administrators only">
          Confidential
        </PropLabel>
        <div className="flex items-center gap-2 h-9">
          <Switch
            checked={project.isConfidential ?? false}
            onCheckedChange={(v) => patch({ isConfidential: v })}
            disabled={!canEdit}
          />
          <span className="text-xs text-etex-gray-600 dark:text-gray-400">
            {project.isConfidential ? "Confidential" : "Not confidential"}
          </span>
        </div>
      </div>
      <div>
        <PropLabel hint="SAP Work Breakdown Structure codes for financial tracking">SAP WBS</PropLabel>
        <WbsInline
          codes={project.wbsCodes ?? []}
          canEdit={canEdit}
          factoryCode={factoryDisplay?.code ?? null}
          onChange={(codes) => patch({ wbsCodes: codes })}
        />
      </div>
    </div>
  );
}

/* ── WbsInline — click-to-edit inline WBS codes ──────────────────────── */

function WbsInline({ codes, canEdit, factoryCode, onChange }: {
  codes: string[];
  canEdit: boolean;
  factoryCode: string | null;
  onChange: (codes: string[]) => void;
}) {
  const [editIdx, setEditIdx] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { if (editIdx !== null) inputRef.current?.select(); }, [editIdx]);

  const commit = () => {
    if (editIdx === null) return;
    const trimmed = draft.trim();
    if (!trimmed) {
      // empty = remove
      onChange(codes.filter((_, i) => i !== editIdx));
    } else {
      const updated = [...codes];
      updated[editIdx] = trimmed;
      onChange(updated);
    }
    setEditIdx(null);
  };

  const startEdit = (idx: number) => {
    setDraft(codes[idx]);
    setEditIdx(idx);
  };

  const addNew = () => {
    const defaultWbs = `O${factoryCode ?? "XXXX"}/2xxx`;
    const next = [...codes, defaultWbs];
    onChange(next);
    setDraft(defaultWbs);
    setEditIdx(next.length - 1);
  };

  const isEmpty = codes.length === 0;

  // Read-only display
  if (!canEdit) {
    return (
      <div className="flex items-center h-9 text-sm font-mono text-muted-foreground tracking-wide">
        {isEmpty ? "—" : codes.join(" · ")}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-0.5 h-9 min-w-0">
      {codes.map((code, idx) =>
        editIdx === idx ? (
          <input
            key={idx}
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit();
              if (e.key === "Escape") setEditIdx(null);
              if (e.key === "Backspace" && !draft) {
                onChange(codes.filter((_, i) => i !== idx));
                setEditIdx(null);
              }
            }}
            className="w-32 bg-transparent border-b border-etex-orange/60 px-0 py-0.5 text-xs font-mono tracking-wide outline-none placeholder:text-muted-foreground/40"
            placeholder="WBS code"
          />
        ) : (
          <span key={idx} className="group/wbs inline-flex items-center">
            {idx > 0 && <span className="text-muted-foreground/30 mx-1 text-xs select-none">·</span>}
            <button
              type="button"
              onClick={() => startEdit(idx)}
              className="text-xs font-mono tracking-wide text-foreground/80 hover:text-etex-orange transition-colors cursor-text"
            >
              {code}
            </button>
            <button
              type="button"
              onClick={() => onChange(codes.filter((_, i) => i !== idx))}
              className="opacity-0 group-hover/wbs:opacity-100 ml-0.5 text-muted-foreground/40 hover:text-red-400 transition-opacity"
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ),
      )}
      {editIdx === null && (
        <button
          type="button"
          onClick={addNew}
          className="ml-1 text-muted-foreground/40 hover:text-etex-orange transition-colors"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}
