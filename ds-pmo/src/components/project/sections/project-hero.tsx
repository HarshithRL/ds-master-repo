"use client";

import { useState } from "react";
import { AutoInput } from "@/components/ui/auto-fields";
import { InfoHint } from "@/components/ui/info-hint";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { formatDate, getInitials } from "@/lib/utils";
import { Eye, FileBarChart, MoreHorizontal, Trash2 } from "lucide-react";
import Link from "next/link";
import type { ProjectWithRelations } from "@/types";

interface ProjectHeroProps {
  project: ProjectWithRelations;
  projectId: string;
  patch: (fields: Record<string, unknown>) => void;
  canEdit: boolean;
  onDelete: () => void;
}

export function ProjectHero({ project, projectId, canEdit, onDelete, patch }: ProjectHeroProps) {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  return (
    <>
      <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
        {/* Title block — name (huge) + reference (subtitle), both inline-editable */}
        <div className="flex-1 min-w-0">
          <AutoInput
            bare
            value={project.name}
            onSave={(v) => patch({ name: v })}
            placeholder="Untitled project"
            className="font-bold text-etex-charcoal dark:text-gray-100 text-2xl sm:text-3xl lg:text-4xl bg-transparent border-none outline-none px-0 py-1 leading-[1.1] tracking-tight focus:ring-0"
          />
          <div className="mt-1.5 flex items-baseline gap-1.5">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground shrink-0 inline-flex items-center gap-0.5">
              Reference
              <InfoHint label="Reference" text="Project code from the Etex Engineering Timesheet. Optional." />
            </span>
            <div className="min-w-0 max-w-xs flex-1">
              <AutoInput
                bare
                value={project.reference ?? ""}
                onSave={(v) => patch({ reference: v || null })}
                placeholder="REF-000"
                className="font-mono font-semibold text-etex-orange text-sm bg-transparent border-none outline-none px-0 py-0 tracking-wide uppercase focus:ring-0"
              />
            </div>
          </div>
        </div>

        {/* Action cluster — status chips above, action buttons below.
            Two-row stack keeps the title block visually dominant. */}
        <div className="flex flex-col items-end gap-1.5 shrink-0">
          {project.lastUpdatedBy && (
            <div className="flex items-center flex-wrap gap-1.5 justify-end">
              <UpdatedChip project={project} />
            </div>
          )}
          <div className="flex items-center flex-wrap gap-1.5 justify-end">
            <Link
              href={`/projects/${projectId}/one-pager`}
              className="inline-flex items-center gap-1.5 h-8 px-3 text-xs font-medium rounded-sm text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-[#333842] bg-white dark:bg-[#21252B] hover:bg-gray-50 hover:border-gray-300 dark:hover:bg-[#282C34] dark:hover:border-[#3D4350] transition-colors"
            >
              <FileBarChart className="w-3.5 h-3.5" />
              One-pager
            </Link>

            {canEdit ? (
              <DropdownMenu>
                <DropdownMenuTrigger
                  className="inline-flex items-center justify-center h-8 w-8 rounded-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-white/5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-etex-orange border border-transparent hover:border-gray-200 dark:hover:border-[#333842]"
                  aria-label="More actions"
                >
                  <MoreHorizontal className="w-4 h-4" />
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-44">
                  <DropdownMenuItem
                    onSelect={() => setShowDeleteConfirm(true)}
                    className="text-red-600 dark:text-red-400 focus:bg-red-50 focus:text-red-700 dark:focus:bg-red-500/10 dark:focus:text-red-300"
                  >
                    <Trash2 className="w-3.5 h-3.5 mr-2" />
                    Delete project
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              <span className="inline-flex items-center gap-1.5 h-8 px-2.5 text-[11px] font-medium text-muted-foreground bg-muted/50 border border-border rounded-sm">
                <Eye className="w-3.5 h-3.5" />
                Read-only
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="border-b border-gray-200 dark:border-[#333842]" />

      <ConfirmDialog
        open={showDeleteConfirm}
        onOpenChange={setShowDeleteConfirm}
        title="Delete project"
        description={`"${project.name}" will be deactivated. It can be restored by an administrator.`}
        confirmLabel="Delete"
        destructive
        onConfirm={onDelete}
      />
    </>
  );
}

/* ── Last-updated chip ─────────────────────────────────────────── */

function UpdatedChip({ project }: { project: ProjectWithRelations }) {
  if (!project.lastUpdatedBy) return null;
  const initials = getInitials(project.lastUpdatedBy.name);
  const date = formatDate(project.updatedAt);

  return (
    <span className="inline-flex items-center gap-2 h-8 pl-1.5 pr-2.5 text-[11px] text-muted-foreground rounded-sm border border-border bg-muted/30 dark:bg-white/2">
      {project.lastUpdatedBy.image ? (
        <img
          src={project.lastUpdatedBy.image}
          alt={project.lastUpdatedBy.name}
          className="w-5 h-5 rounded-sm object-cover ring-1 ring-gray-200 dark:ring-[#333842]"
        />
      ) : (
        <span className="w-5 h-5 rounded-sm bg-etex-orange/15 text-etex-orange text-[9px] font-bold flex items-center justify-center ring-1 ring-etex-orange/20">
          {initials}
        </span>
      )}
      <span>
        Updated by <span className="font-medium text-foreground">{project.lastUpdatedBy.name}</span> · {date}
      </span>
    </span>
  );
}
