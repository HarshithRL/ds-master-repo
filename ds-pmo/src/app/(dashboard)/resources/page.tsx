"use client";

import { useEffect, useMemo, useState } from "react";
import { ExternalLink, Loader2, Pencil, Plus, Search, Trash2, X } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { AdminFormDialog } from "@/components/admin/admin-form-dialog";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useSessionUser } from "@/components/layout/session-context";
import { api } from "@/lib/api";
import type { Resource } from "@/lib/db/models";
import { getCategoryStyle, type CategoryStyle } from "@/lib/resources-data";
import { cn } from "@/lib/utils";

// ─── Format badge ────────────────────────────────────────────────────────────

const FORMAT_STYLES: Record<string, string> = {
  PDF: "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-400 ring-red-200 dark:ring-red-500/20",
  XLSX: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400 ring-emerald-200 dark:ring-emerald-500/20",
  PPTX: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400 ring-amber-200 dark:ring-amber-500/20",
  DOCX: "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400 ring-blue-200 dark:ring-blue-500/20",
  Link: "bg-gray-100 text-gray-600 dark:bg-gray-500/10 dark:text-gray-400 ring-gray-200 dark:ring-gray-500/20",
};

/** The only formats selectable when adding/editing a resource. */
const FORMAT_OPTIONS = ["PDF", "PPTX", "XLSX", "DOCX", "Link"] as const;
const FORMAT_SELECT_NONE = "__none__";

function FormatBadge({ format }: { format?: string | null }) {
  if (!format) return null;
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded-sm ring-1 shrink-0",
        FORMAT_STYLES[format] ?? FORMAT_STYLES.Link
      )}
    >
      {format}
    </span>
  );
}

// ─── Category group (derived client-side from the flat resource list) ───────

interface CategoryGroup {
  title: string;
  style: CategoryStyle;
  items: Resource[];
}

// ─── Tab button ──────────────────────────────────────────────────────────────

function TabButton({
  group,
  active,
  onClick,
}: {
  group: CategoryGroup;
  active: boolean;
  onClick: () => void;
}) {
  const Icon = group.style.icon;
  const tc = group.style.tabColors;

  return (
    <button
      onClick={onClick}
      className={cn(
        "relative flex items-center gap-2 px-4 py-2.5 text-[13px] font-semibold rounded-md cursor-pointer transition-all duration-200 whitespace-nowrap select-none border",
        active
          ? cn(tc.bg, tc.border, tc.text)
          : cn("border-transparent text-gray-400 dark:text-gray-500", tc.hoverBg, "hover:text-gray-600 dark:hover:text-gray-300")
      )}
    >
      <Icon
        className={cn(
          "w-4 h-4 shrink-0 transition-colors duration-200",
          active ? group.style.accent : ""
        )}
      />
      <span>{group.title}</span>
      <span
        className={cn(
          "text-[10px] font-bold tabular-nums px-1.5 py-0.5 rounded-sm transition-colors duration-200",
          active
            ? cn(tc.countBg, tc.countText)
            : "bg-gray-100 text-gray-400 dark:bg-white/5 dark:text-gray-500"
        )}
      >
        {group.items.length}
      </span>
    </button>
  );
}

// ─── Table row ───────────────────────────────────────────────────────────────

function ResourceRow({
  item,
  index,
  canEdit,
  onEdit,
  onRemove,
}: {
  item: Resource;
  index: number;
  canEdit: boolean;
  onEdit: () => void;
  onRemove: () => void;
}) {
  return (
    <div
      className={cn(
        "group grid grid-cols-[1fr_auto_auto] items-center gap-4 px-4 py-3 transition-colors duration-150",
        index % 2 === 0 ? "bg-white dark:bg-transparent" : "bg-gray-50/60 dark:bg-white/2",
        "hover:bg-etex-orange-50/50 dark:hover:bg-etex-orange/5"
      )}
    >
      {/* Name + description */}
      <div className="min-w-0">
        <a
          href={item.href}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 max-w-full text-[13px] font-semibold text-gray-900 dark:text-gray-100 hover:text-etex-orange dark:hover:text-etex-orange-light transition-colors"
        >
          <span className="truncate">{item.title}</span>
          <ExternalLink className="w-3 h-3 text-gray-300 dark:text-gray-600 shrink-0" />
        </a>
        {item.description && (
          <p className="text-xs text-gray-500 dark:text-gray-400 truncate mt-0.5">
            {item.description}
          </p>
        )}
      </div>

      {/* Format */}
      <FormatBadge format={item.format} />

      {/* Admin actions (view-only users get an empty spacer to keep columns aligned) */}
      {canEdit ? (
        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
          <button
            onClick={onEdit}
            title="Edit resource"
            className="p-1.5 rounded text-gray-400 hover:text-etex-orange hover:bg-etex-orange-50 dark:hover:bg-etex-orange/10 transition-colors cursor-pointer"
          >
            <Pencil className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={onRemove}
            title="Remove resource"
            className="p-1.5 rounded text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors cursor-pointer"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      ) : (
        <span className="w-3.5" />
      )}
    </div>
  );
}

// ─── Add/Edit form ────────────────────────────────────────────────────────────

interface ResourceFormValues {
  category: string;
  title: string;
  description: string;
  href: string;
  format: string;
}

function ResourceFormDialog({
  title,
  submitLabel,
  initial,
  categoryOptions,
  error,
  submitting,
  onCancel,
  onSubmit,
}: {
  title: string;
  submitLabel: string;
  initial: ResourceFormValues;
  categoryOptions: string[];
  error: string | null;
  submitting: boolean;
  onCancel: () => void;
  onSubmit: (values: ResourceFormValues) => void;
}) {
  const [values, setValues] = useState<ResourceFormValues>(initial);
  const set = <K extends keyof ResourceFormValues>(key: K, v: ResourceFormValues[K]) =>
    setValues((p) => ({ ...p, [key]: v }));

  return (
    <AdminFormDialog
      open
      onOpenChange={(v) => !v && onCancel()}
      title={title}
      submitLabel={submitLabel}
      submitting={submitting}
      submitDisabled={!values.category.trim() || !values.title.trim() || !values.href.trim()}
      error={error}
      maxWidth="max-w-md"
      onSubmit={() => onSubmit(values)}
    >
      <div className="space-y-3">
        <div>
          <Label className="text-xs font-medium">Category</Label>
          <Input
            list="resource-category-options"
            value={values.category}
            onChange={(e) => set("category", e.target.value)}
            placeholder="e.g. Project Lifecycle"
            className="rounded-sm mt-1 text-sm h-8"
          />
          <datalist id="resource-category-options">
            {categoryOptions.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
        </div>
        <div>
          <Label className="text-xs font-medium">Title</Label>
          <Input
            value={values.title}
            onChange={(e) => set("title", e.target.value)}
            placeholder="Document name"
            className="rounded-sm mt-1 text-sm h-8"
          />
        </div>
        <div>
          <Label className="text-xs font-medium">Description</Label>
          <Textarea
            value={values.description}
            onChange={(e) => set("description", e.target.value)}
            placeholder="Short description shown under the title"
            rows={2}
            className="rounded-sm mt-1 text-sm"
          />
        </div>
        <div>
          <Label className="text-xs font-medium">Link</Label>
          <Input
            value={values.href}
            onChange={(e) => set("href", e.target.value)}
            placeholder="https://..."
            className="rounded-sm mt-1 text-sm h-8"
          />
        </div>
        <div>
          <Label className="text-xs font-medium">Format</Label>
          <Select
            value={values.format || FORMAT_SELECT_NONE}
            onValueChange={(v) => set("format", v === FORMAT_SELECT_NONE ? "" : v)}
          >
            <SelectTrigger className="rounded-sm mt-1 text-sm h-8">
              <SelectValue placeholder="Select a format…" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={FORMAT_SELECT_NONE}>— None —</SelectItem>
              {FORMAT_OPTIONS.map((f) => (
                <SelectItem key={f} value={f}>
                  {f}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
    </AdminFormDialog>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

const EMPTY_FORM: ResourceFormValues = { category: "", title: "", description: "", href: "", format: "" };

export default function ResourcesPage() {
  const sessionUser = useSessionUser();
  const canEdit =
    sessionUser?.globalRole === "ADMIN" ||
    (sessionUser?.permissions.includes("MANAGE_RESOURCES") ?? false);

  const [resources, setResources] = useState<Resource[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const [addOpen, setAddOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<Resource | null>(null);
  const [removeTarget, setRemoveTarget] = useState<Resource | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const load = () => {
    setLoading(true);
    api
      .get<Resource[]>("/api/resources")
      .then((data) => {
        setResources(data);
        setLoadError(null);
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : "Failed to load resources"))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  // Group by category, ordered by each category's earliest-created resource
  // (stable, predictable ordering that doesn't jump around as rows are edited).
  const groups: CategoryGroup[] = useMemo(() => {
    const byCategory = new Map<string, Resource[]>();
    for (const r of resources) {
      const list = byCategory.get(r.category);
      if (list) list.push(r);
      else byCategory.set(r.category, [r]);
    }
    const entries = Array.from(byCategory.entries()).map(([title, items]) => ({
      title,
      style: getCategoryStyle(title),
      items,
      earliest: items.reduce((min, r) => Math.min(min, new Date(r.createdAt).getTime()), Infinity),
    }));
    entries.sort((a, b) => a.earliest - b.earliest);
    return entries.map(({ title, style, items }) => ({ title, style, items }));
  }, [resources]);

  const categoryNames = useMemo(() => groups.map((g) => g.title), [groups]);

  const activeGroup = groups.find((g) => g.title === activeCategory) ?? groups[0] ?? null;

  const filteredItems = (activeGroup ? activeGroup.items : []).filter((item) =>
    search.trim()
      ? item.title.toLowerCase().includes(search.toLowerCase()) ||
        (item.description ?? "").toLowerCase().includes(search.toLowerCase()) ||
        (item.format ?? "").toLowerCase().includes(search.toLowerCase())
      : true
  );

  const totalDocs = resources.length;

  const submitAdd = async (values: ResourceFormValues) => {
    setSubmitting(true);
    setFormError(null);
    try {
      const created = await api.post<Resource>("/api/admin/resources", {
        category: values.category.trim(),
        title: values.title.trim(),
        description: values.description.trim() || null,
        href: values.href.trim(),
        format: values.format.trim() || null,
      });
      setResources((p) => [...p, created]);
      setActiveCategory(created.category);
      setAddOpen(false);
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed to create resource");
    } finally {
      setSubmitting(false);
    }
  };

  const submitEdit = async (values: ResourceFormValues) => {
    if (!editTarget) return;
    setSubmitting(true);
    setFormError(null);
    try {
      const updated = await api.put<Resource>(`/api/admin/resources/${editTarget.id}`, {
        category: values.category.trim(),
        title: values.title.trim(),
        description: values.description.trim() || null,
        href: values.href.trim(),
        format: values.format.trim() || null,
      });
      setResources((p) => p.map((r) => (r.id === updated.id ? updated : r)));
      setActiveCategory(updated.category);
      setEditTarget(null);
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed to update resource");
    } finally {
      setSubmitting(false);
    }
  };

  const confirmRemove = async () => {
    if (!removeTarget) return;
    setSubmitting(true);
    try {
      await api.delete(`/api/admin/resources/${removeTarget.id}`);
      setResources((p) => p.filter((r) => r.id !== removeTarget.id));
      setRemoveTarget(null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Failed to remove resource");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Resources"
        subtitle={loading ? "Loading…" : `${totalDocs} document${totalDocs === 1 ? "" : "s"} across ${groups.length} categor${groups.length === 1 ? "y" : "ies"}`}
      >
        {canEdit && (
          <button
            onClick={() => setAddOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-etex-orange hover:bg-etex-orange-dark text-white text-xs font-semibold transition-colors cursor-pointer shrink-0"
          >
            <Plus className="w-3.5 h-3.5" />
            Add Resource
          </button>
        )}
      </PageHeader>

      {loadError && (
        <div className="p-3 mb-4 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-800 rounded-sm text-sm text-red-700 dark:text-red-400">
          {loadError}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20 text-gray-400">
          <Loader2 className="w-5 h-5 animate-spin" />
        </div>
      ) : groups.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center border border-dashed border-gray-200 dark:border-[#333842] rounded-md">
          <p className="text-sm font-medium text-gray-500 dark:text-gray-400">No resources yet</p>
          {canEdit && (
            <button
              onClick={() => setAddOpen(true)}
              className="mt-2 text-xs text-etex-orange hover:underline cursor-pointer"
            >
              Add the first one
            </button>
          )}
        </div>
      ) : (
        <>
          {/* Tabs */}
          <div className="flex items-center gap-2 overflow-x-auto pb-1 mb-5 scrollbar-none">
            {groups.map((g) => (
              <TabButton
                key={g.title}
                group={g}
                active={g.title === activeGroup?.title}
                onClick={() => {
                  setActiveCategory(g.title);
                  setSearch("");
                }}
              />
            ))}
          </div>

          {/* Toolbar: search + count */}
          <div className="flex items-center justify-between gap-4 mb-4">
            <div className="relative max-w-xs flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500 pointer-events-none z-10" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={`Search in ${activeGroup?.title ?? ""}...`}
                className="form-control w-full pl-10! pr-8"
              />
              {search && (
                <button
                  onClick={() => setSearch("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 cursor-pointer transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
            <span className="text-xs font-medium text-gray-400 dark:text-gray-500 tabular-nums shrink-0">
              {filteredItems.length} {filteredItems.length === 1 ? "document" : "documents"}
            </span>
          </div>

          {/* Table */}
          <div className="border border-gray-200 dark:border-[#333842] rounded-md overflow-hidden bg-white dark:bg-[#1E2128] shadow-sm dark:shadow-black/20">
            {/* Table header */}
            <div className="grid grid-cols-[1fr_auto_auto] items-center gap-4 px-4 py-2.5 bg-gray-900 dark:bg-etex-charcoal">
              <span className="text-[10px] font-semibold uppercase tracking-widest text-gray-300 dark:text-gray-400">
                Document
              </span>
              <span className="text-[10px] font-semibold uppercase tracking-widest text-gray-300 dark:text-gray-400">
                Format
              </span>
              <span className="w-3.5" />
            </div>

            {/* Rows */}
            {filteredItems.length > 0 ? (
              <div className="divide-y divide-gray-100 dark:divide-[#2A2F38]">
                {filteredItems.map((item, i) => (
                  <ResourceRow
                    key={item.id}
                    item={item}
                    index={i}
                    canEdit={canEdit}
                    onEdit={() => setEditTarget(item)}
                    onRemove={() => setRemoveTarget(item)}
                  />
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-14 text-center">
                <Search className="w-7 h-7 text-gray-300 dark:text-gray-600 mb-2" />
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                  No documents match your search
                </p>
                <button
                  onClick={() => setSearch("")}
                  className="mt-2 text-xs text-etex-orange hover:underline cursor-pointer"
                >
                  Clear search
                </button>
              </div>
            )}
          </div>
        </>
      )}

      {addOpen && (
        <ResourceFormDialog
          title="Add Resource"
          submitLabel="Add Resource"
          initial={{ ...EMPTY_FORM, category: activeGroup?.title ?? "" }}
          categoryOptions={categoryNames}
          error={formError}
          submitting={submitting}
          onCancel={() => {
            setAddOpen(false);
            setFormError(null);
          }}
          onSubmit={submitAdd}
        />
      )}

      {editTarget && (
        <ResourceFormDialog
          title={`Edit resource: ${editTarget.title}`}
          submitLabel="Save Changes"
          initial={{
            category: editTarget.category,
            title: editTarget.title,
            description: editTarget.description ?? "",
            href: editTarget.href,
            format: editTarget.format ?? "",
          }}
          categoryOptions={categoryNames}
          error={formError}
          submitting={submitting}
          onCancel={() => {
            setEditTarget(null);
            setFormError(null);
          }}
          onSubmit={submitEdit}
        />
      )}

      {removeTarget && (
        <ConfirmDialog
          open
          onOpenChange={(v) => !v && setRemoveTarget(null)}
          title="Remove resource"
          description={`"${removeTarget.title}" will be permanently deleted.`}
          confirmLabel="Remove"
          destructive
          onConfirm={confirmRemove}
        />
      )}
    </>
  );
}
