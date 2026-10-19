"use client";

import { useMemo } from "react";
import { Plus, Trash2, ExternalLink } from "lucide-react";
import { AutoInput } from "@/components/ui/auto-fields";
import { DataGrid, type DataGridColumn } from "@/components/ui/data-grid";
import { useOptimisticList } from "@/hooks/use-optimistic-list";
import { useReadOnly } from "@/components/ui/read-only-context";
import type { ProjectDocument } from "@/lib/db/models";

/* ═══════════════════════════════════════════════════════════════════
   DocumentsTab — unified table with fixed + custom document rows

   Fixed rows (Schedule, Cost, RIAC) are always present at the top.
   "Delete" on a fixed row clears its URL; the row itself stays.
   Custom rows can be fully added/removed.
   ═══════════════════════════════════════════════════════════════════ */

/* ── Unified row type ──────────────────────────────────────────── */

type DocRow = {
  id: string;
  name: string;
  url: string;
  fixed: boolean;
  field?: "scheduleDocUrl" | "costDocUrl" | "riacDocUrl";
};

/* ── Fixed document definitions ────────────────────────────────── */

const FIXED_DOCS: { label: string; field: "scheduleDocUrl" | "costDocUrl" | "riacDocUrl" }[] = [
  { label: "Schedule", field: "scheduleDocUrl" },
  { label: "Cost", field: "costDocUrl" },
  { label: "RIAC", field: "riacDocUrl" },
];

// Render-time guard: anchor hrefs that aren't http(s) (e.g. `javascript:`)
// can execute script on click. The server-side schema already enforces this,
// but stale rows pre-dating the schema may still hold unsafe values.
function safeHref(url: string): string | undefined {
  return /^https?:\/\//i.test(url) ? url : undefined;
}

/* ── Props ──────────────────────────────────────────────────────── */

interface DocumentsTabProps {
  projectId: string;
  /** Fixed doc URLs from the project record */
  fixedUrls: {
    scheduleDocUrl: string | null;
    costDocUrl: string | null;
    riacDocUrl: string | null;
  };
  /** Callback to patch a project-level field (fixed docs) */
  onPatchProject: (data: Record<string, unknown>) => void;
  /** Custom documents from the ProjectDocument table */
  documents: ProjectDocument[];
}

export function DocumentsTab({
  projectId,
  fixedUrls,
  onPatchProject,
  documents: propDocuments,
}: DocumentsTabProps) {
  const readOnly = useReadOnly();
  const baseUrl = `/api/projects/${projectId}/documents`;

  const createOptimistic = useMemo(
    () => () =>
      ({
        id: `_tmp_${Date.now()}`,
        projectId,
        name: "",
        url: "",
        sortOrder: 0,
        createdAt: new Date(),
        updatedAt: new Date(),
      }) as ProjectDocument,
    [projectId],
  );

  const createPayload = useMemo(
    () => () => ({ name: "", url: "" }),
    [],
  );

  const { items: customItems, add, patch: patchCustom, remove } = useOptimisticList<ProjectDocument>({
    initial: propDocuments,
    baseUrl,
    createOptimistic,
    createPayload,
  });

  /* ── Merge fixed + custom rows ────────────────────────────────── */

  const rows: DocRow[] = useMemo(() => {
    const fixed: DocRow[] = FIXED_DOCS.map((d) => ({
      id: `_fixed_${d.field}`,
      name: d.label,
      url: fixedUrls[d.field] ?? "",
      fixed: true,
      field: d.field,
    }));

    const custom: DocRow[] = customItems.map((d) => ({
      id: d.id,
      name: d.name,
      url: d.url,
      fixed: false,
    }));

    return [...fixed, ...custom];
  }, [fixedUrls, customItems]);

  /* ── Column definitions ───────────────────────────────────────── */

  const columns: DataGridColumn<DocRow>[] = useMemo(() => [
    {
      id: "name",
      header: "Name",
      hint: "Document label or title",
      width: "minmax(0,1fr)",
      renderEdit: (d) =>
        d.fixed ? (
          <span className="text-foreground font-medium px-2 h-9 flex items-center">{d.name}</span>
        ) : (
          <AutoInput
            value={d.name}
            onSave={(v) => patchCustom(d.id, "name", v)}
            placeholder="Document name"
          />
        ),
      render: (d) => (
        <span className="text-foreground">{d.name || <span className="text-muted-foreground">—</span>}</span>
      ),
    },
    {
      id: "url",
      header: "URL",
      hint: "Link to the document",
      width: "minmax(0,2fr)",
      renderEdit: (d) =>
        d.fixed ? (
          <AutoInput
            value={d.url}
            onSave={(v) => onPatchProject({ [d.field!]: v || null })}
            placeholder="Paste URL"
          />
        ) : (
          <AutoInput
            value={d.url}
            onSave={(v) => patchCustom(d.id, "url", v)}
            placeholder="https://..."
          />
        ),
      render: (d) => {
        if (!d.url) return <span className="text-muted-foreground">—</span>;
        return (
          <span className="font-mono text-muted-foreground text-sm truncate block">{d.url}</span>
        );
      },
    },
    {
      id: "view",
      header: "",
      width: "28px",
      render: (d) => {
        const href = safeHref(d.url);
        if (!href) return null;
        return (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted-foreground hover:text-etex-orange transition-colors p-1 rounded inline-flex"
          >
            <ExternalLink size={13} />
          </a>
        );
      },
      renderEdit: (d) => {
        const href = safeHref(d.url);
        if (!href) return null;
        return (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted-foreground hover:text-etex-orange transition-colors p-1 rounded inline-flex"
          >
            <ExternalLink size={13} />
          </a>
        );
      },
    },
    {
      id: "actions",
      header: "",
      width: "28px",
      render: () => null,
      renderEdit: (d) => {
        if (d.fixed) {
          // Clear URL instead of removing the row
          if (!d.url) return null;
          return (
            <button
              onClick={() => onPatchProject({ [d.field!]: null })}
              className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-danger transition-all p-1 rounded"
            >
              <Trash2 size={13} />
            </button>
          );
        }
        return (
          <button
            onClick={() => remove(d.id)}
            className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-danger transition-all p-1 rounded"
          >
            <Trash2 size={13} />
          </button>
        );
      },
    },
  ], [patchCustom, remove, onPatchProject]);

  return (
    <DataGrid
      columns={columns}
      data={rows}
      editable={!readOnly}
      rowKey={(d) => d.id}
      emptyMessage="No documents yet."
      footer={
        !readOnly ? (
          <button
            onClick={add}
            className="flex items-center gap-1.5 w-full px-4 py-2.5 text-[12px] text-muted-foreground
                       hover:text-etex-orange hover:bg-etex-orange-50 transition-colors"
          >
            <Plus size={13} />
            Add document
          </button>
        ) : undefined
      }
    />
  );
}
