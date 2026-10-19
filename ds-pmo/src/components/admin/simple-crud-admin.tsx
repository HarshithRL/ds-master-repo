"use client";

/* ═══════════════════════════════════════════════════════════════════
   SimpleCrudAdmin — reusable list/create/edit/delete screen.

   Backs the Factories & Categories admin pages — any future small
   admin entity (divisions, tags, etc.) can plug in via the same
   props without re-implementing the boilerplate.
   ═══════════════════════════════════════════════════════════════════ */

import { useState } from "react";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { InfoHint } from "@/components/ui/info-hint";
import { PageHeader } from "@/components/layout/page-header";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";
import { AdminFormDialog } from "@/components/admin/admin-form-dialog";
import { RowActions } from "@/components/admin/admin-shared";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAdminResource } from "@/hooks/use-admin-resource";
import { cn } from "@/lib/utils";

/* ── Form field definition ──────────────────────────────────────────── */

const SELECT_NONE = "__none__";

export type FormField = {
  key: string;
  label: string;
  hint?: string;
  /** Disable on edit (e.g., immutable "code"). */
  immutableOnEdit?: boolean;
  placeholder?: string;
  /** Render a Select instead of an Input. */
  options?: { value: string; label: string }[];
  /** If true, include an explicit "— None —" option that maps to "". */
  nullable?: boolean;
};

/* ── Props ──────────────────────────────────────────────────────────── */

export interface SimpleCrudAdminProps<T extends { id: string }> {
  /** Page chrome */
  title: string;
  subtitle: string;
  addLabel: string;
  searchPlaceholder: string;
  emptyTitle: string;
  emptyMessage: string;
  /** API endpoint base — POST {}, PUT {id}, DELETE {id} relative to this. */
  endpoint: string;
  /** Columns for the DataTable. `actions` column is added automatically. */
  columns: DataTableColumn<T>[];
  /** Fields shown in the add/edit dialog. */
  addFields: FormField[];
  /** Fields shown in the edit dialog (defaults to addFields). */
  editFields?: FormField[];
  /** Initial form values (defaults: empty strings). */
  defaults?: Record<string, string>;
  /** Build the edit-dialog values from the row. */
  toEditValues: (row: T) => Record<string, string>;
  /** Compose the edit-dialog title. */
  editTitle: (row: T) => string;
  /** Optional client-side filter — defaults to a case-insensitive substring across edit values. */
  filterRow?: (row: T, query: string) => boolean;
  /** Confirmation copy when deleting. */
  removeWarning: (row: T) => string;
  /** Invalidate the reference data cache after writes (default true). */
  invalidatesReferenceData?: boolean;
  /** Final transform applied to form values before they hit the API (e.g., "" → null). */
  transformValues?: (values: Record<string, string>) => Record<string, unknown>;
}

/* ── Component ──────────────────────────────────────────────────────── */

export function SimpleCrudAdmin<T extends { id: string }>({
  title,
  subtitle,
  addLabel,
  searchPlaceholder,
  emptyTitle,
  emptyMessage,
  endpoint,
  columns,
  addFields,
  editFields,
  defaults,
  toEditValues,
  editTitle,
  filterRow,
  removeWarning,
  invalidatesReferenceData = true,
  transformValues,
}: SimpleCrudAdminProps<T>) {
  const { rows, loading, error, setError, add, update, remove } =
    useAdminResource<T>({ endpoint, invalidatesReferenceData });

  const [search, setSearch] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<T | null>(null);
  const [removeTarget, setRemoveTarget] = useState<T | null>(null);

  /* Filter */
  const filtered = search
    ? rows.filter((r) => {
        if (filterRow) return filterRow(r, search);
        const q = search.toLowerCase();
        return Object.values(toEditValues(r)).some((v) =>
          String(v ?? "").toLowerCase().includes(q),
        );
      })
    : rows;

  /* Compose columns with auto-injected actions */
  const fullColumns: DataTableColumn<T>[] = [
    ...columns,
    {
      key: "actions",
      header: "",
      align: "right",
      width: "100px",
      render: (row) => (
        <RowActions
          onEdit={() => setEditTarget(row)}
          onRemove={() => setRemoveTarget(row)}
        />
      ),
    },
  ];

  return (
    <>
      <PageHeader title={title} subtitle={subtitle}>
        <Button
          onClick={() => setAddOpen(true)}
          className="bg-etex-orange hover:bg-etex-orange-dark text-white text-xs h-8 shrink-0"
        >
          <Plus className="w-3.5 h-3.5 mr-1.5" />
          {addLabel}
        </Button>
      </PageHeader>

      {error && !addOpen && !editTarget && (
        <div className="p-3 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-800 rounded-sm text-sm text-red-700 dark:text-red-400">
          {error}
        </div>
      )}

      <DataTable
        columns={fullColumns}
        data={filtered}
        rowKey={(r) => r.id}
        loading={loading}
        emptyTitle={emptyTitle}
        emptyMessage={emptyMessage}
        toolbar={{
          search: { value: search, onChange: setSearch, placeholder: searchPlaceholder },
        }}
      />

      {addOpen && (
        <CrudFormDialog
          key="crud-add"
          title={addLabel}
          submitLabel={addLabel}
          fields={addFields}
          initial={defaults ?? {}}
          error={error}
          onCancel={() => {
            setAddOpen(false);
            setError(null);
          }}
          onSubmit={async (vals) => {
            const payload = transformValues ? transformValues(vals) : vals;
            const created = await add(payload);
            if (created) setAddOpen(false);
          }}
        />
      )}

      {editTarget && (
        <CrudFormDialog
          key={`crud-edit-${editTarget.id}`}
          title={editTitle(editTarget)}
          submitLabel="Save Changes"
          fields={editFields ?? addFields}
          initial={toEditValues(editTarget)}
          error={error}
          isEdit
          onCancel={() => {
            setEditTarget(null);
            setError(null);
          }}
          onSubmit={async (vals) => {
            const payload = transformValues ? transformValues(vals) : vals;
            const updated = await update(editTarget.id, payload);
            if (updated) setEditTarget(null);
          }}
        />
      )}

      {removeTarget && (
        <ConfirmDialog
          open
          onOpenChange={(v) => !v && setRemoveTarget(null)}
          title={`Remove ${title.toLowerCase()}`}
          description={removeWarning(removeTarget)}
          confirmLabel="Remove"
          destructive
          onConfirm={async () => {
            const ok = await remove(removeTarget.id);
            if (ok) setRemoveTarget(null);
          }}
        />
      )}
    </>
  );
}

/* ── Self-contained add/edit dialog ──────────────────────────────────
   Owns its own form state. Parent remounts it via `key` to reset.    */

function CrudFormDialog({
  title,
  submitLabel,
  fields,
  initial,
  error,
  isEdit,
  onCancel,
  onSubmit,
}: {
  title: string;
  submitLabel: string;
  fields: FormField[];
  initial: Record<string, string>;
  error: string | null;
  isEdit?: boolean;
  onCancel: () => void;
  onSubmit: (values: Record<string, string>) => Promise<void> | void;
}) {
  const [values, setValues] = useState<Record<string, string>>(initial);

  return (
    <AdminFormDialog
      open
      onOpenChange={(v) => !v && onCancel()}
      title={title}
      submitLabel={submitLabel}
      onSubmit={() => onSubmit(values)}
      error={error}
      maxWidth="max-w-sm"
    >
      <div className="space-y-3">
        {fields.map((f) => {
          const { key, label, hint, immutableOnEdit, placeholder } = f;
          const disabled = !!(isEdit && immutableOnEdit);
          return (
            <div key={key}>
              <Label className="text-xs font-medium inline-flex items-center gap-1">
                {label}
                {hint && <InfoHint label={label} text={hint} />}
              </Label>
              {f.options ? (
                <Select
                  value={values[key] ? values[key] : SELECT_NONE}
                  disabled={disabled}
                  onValueChange={(v) =>
                    setValues((p) => ({
                      ...p,
                      [key]: v === SELECT_NONE ? "" : v,
                    }))
                  }
                >
                  <SelectTrigger
                    className={cn(
                      "rounded-sm mt-1 text-sm h-8",
                      disabled && "bg-muted text-muted-foreground",
                    )}
                  >
                    <SelectValue placeholder={placeholder ?? "Select…"} />
                  </SelectTrigger>
                  <SelectContent>
                    {f.nullable && (
                      <SelectItem value={SELECT_NONE}>— None —</SelectItem>
                    )}
                    {f.options.map((o) => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <Input
                  value={values[key] ?? ""}
                  disabled={disabled}
                  placeholder={placeholder}
                  onChange={(e) =>
                    setValues((p) => ({ ...p, [key]: e.target.value }))
                  }
                  className={cn(
                    "rounded-sm mt-1 text-sm h-8",
                    disabled && "bg-muted text-muted-foreground",
                  )}
                />
              )}
            </div>
          );
        })}
      </div>
    </AdminFormDialog>
  );
}
