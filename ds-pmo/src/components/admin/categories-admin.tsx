"use client";

import {
  SimpleCrudAdmin,
  type FormField,
} from "@/components/admin/simple-crud-admin";
import type { DataTableColumn } from "@/components/ui/data-table";
import type { Category } from "@/lib/db/models";

type CategoryRow = Category & { _count?: { projects: number } };

const ADD_FIELDS: FormField[] = [
  { key: "code", label: "Code", hint: "Unique short code for this category" },
  { key: "name", label: "Name", hint: "Descriptive category name shown in dropdowns" },
];

const EDIT_FIELDS: FormField[] = [
  { ...ADD_FIELDS[0], immutableOnEdit: true },
  ADD_FIELDS[1],
];

const columns: DataTableColumn<CategoryRow>[] = [
  {
    key: "code",
    header: "Code",
    sortable: true,
    sortValue: (r) => r.code,
    render: (c) => (
      <span className="font-mono font-medium text-foreground">{c.code}</span>
    ),
    width: "120px",
  },
  {
    key: "name",
    header: "Name",
    sortable: true,
    sortValue: (r) => r.name,
    render: (c) => <span className="truncate">{c.name}</span>,
  },
  {
    key: "projects",
    header: "# Projects",
    align: "right",
    numeric: true,
    sortable: true,
    sortValue: (r) => r._count?.projects ?? 0,
    render: (c) => (c._count?.projects ?? 0).toString(),
    width: "120px",
  },
];

export function CategoriesAdmin() {
  return (
    <SimpleCrudAdmin<CategoryRow>
      title="Categories"
      subtitle="Manage project categories"
      addLabel="Add Category"
      searchPlaceholder="Search by code or name..."
      emptyTitle="No categories yet"
      emptyMessage="Add categories so projects can be classified and filtered."
      endpoint="/api/admin/categories"
      columns={columns}
      addFields={ADD_FIELDS}
      editFields={EDIT_FIELDS}
      defaults={{ code: "", name: "" }}
      toEditValues={(c) => ({ code: c.code, name: c.name })}
      editTitle={(c) => `Edit category: ${c.code}`}
      removeWarning={(c) =>
        `"${c.name}" will be permanently deleted. Projects using this category will need to be reassigned.`
      }
    />
  );
}
