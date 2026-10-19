"use client";

import { useEffect, useState } from "react";

import { CountryFlag } from "@/components/ui/country-flag";
import {
  SimpleCrudAdmin,
  type FormField,
} from "@/components/admin/simple-crud-admin";
import { StatusBadge } from "@/components/admin/admin-shared";
import type { DataTableColumn } from "@/components/ui/data-table";
import type { Division, Factory } from "@/lib/db/models";

type FactoryRow = Factory & {
  division?: Division | null;
  _count?: { projects: number };
};

type DivisionOption = { id: string; name: string };

const BASE_FIELDS: FormField[] = [
  { key: "code", label: "Code", hint: "Optional plant code (e.g. 1040, 7461)", placeholder: "1040" },
  { key: "name", label: "Name", hint: "Full factory or site name" },
  { key: "shortName", label: "Short name", hint: "Abbreviated name for compact displays" },
  { key: "country", label: "Country", hint: "ISO 3166-1 alpha-2 (BE, FR, …)", placeholder: "BE" },
  { key: "currency", label: "Currency", hint: "Local currency used for budget reporting", placeholder: "EUR" },
];

const DEFAULTS = { code: "", name: "", shortName: "", country: "", currency: "", divisionId: "" };

const columns: DataTableColumn<FactoryRow>[] = [
  {
    key: "code",
    header: "Code",
    sortable: true,
    sortValue: (r) => r.shortName ?? r.code ?? "",
    render: (f) => (
      <span className="font-mono font-medium text-foreground">
        {f.shortName || f.code || "—"}
      </span>
    ),
    width: "120px",
  },
  {
    key: "name",
    header: "Name",
    sortable: true,
    sortValue: (r) => r.name,
    render: (f) => <span className="truncate">{f.name}</span>,
  },
  {
    key: "country",
    header: "Country",
    sortable: true,
    sortValue: (r) => r.country ?? "",
    render: (f) =>
      f.country ? (
        <span className="inline-flex items-center gap-1.5">
          <CountryFlag code={f.country} size={16} className="rounded-sm" />
          <span className="font-mono text-[11px] uppercase">{f.country}</span>
        </span>
      ) : (
        <span className="text-muted-foreground">—</span>
      ),
    width: "130px",
    hideBelowSm: true,
  },
  {
    key: "division",
    header: "Division",
    sortable: true,
    sortValue: (r) => r.division?.name ?? "",
    render: (f) =>
      f.division ? (
        <StatusBadge label={f.division.name.toUpperCase()} tone="info" />
      ) : (
        <span className="text-muted-foreground">—</span>
      ),
    hideBelowSm: true,
  },
  {
    key: "currency",
    header: "Currency",
    sortable: true,
    sortValue: (r) => r.currency ?? "",
    render: (f) => (
      <span className="font-mono text-[11px] text-muted-foreground">
        {f.currency || "—"}
      </span>
    ),
    width: "110px",
    hideBelowSm: true,
  },
  {
    key: "projects",
    header: "# Projects",
    align: "right",
    numeric: true,
    sortable: true,
    sortValue: (r) => r._count?.projects ?? 0,
    render: (f) => (f._count?.projects ?? 0).toString(),
    width: "110px",
  },
];

export function FactoriesAdmin() {
  const [divisions, setDivisions] = useState<DivisionOption[]>([]);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/admin/factories/divisions")
      .then((r) => (r.ok ? r.json() : []))
      .then((data: DivisionOption[]) => {
        if (!cancelled) setDivisions(data);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const fields: FormField[] = [
    ...BASE_FIELDS,
    {
      key: "divisionId",
      label: "Division",
      hint: "Business division this factory belongs to.",
      nullable: true,
      options: divisions.map((d) => ({ value: d.id, label: d.name })),
    },
  ];

  return (
    <SimpleCrudAdmin<FactoryRow>
      title="Factories"
      subtitle="Manage factory locations"
      addLabel="Add Factory"
      searchPlaceholder="Search by code, name or country..."
      emptyTitle="No factories yet"
      emptyMessage="Add the first factory to start onboarding projects."
      endpoint="/api/admin/factories"
      columns={columns}
      addFields={fields}
      defaults={DEFAULTS}
      toEditValues={(f) => ({
        code: f.code ?? "",
        name: f.name,
        shortName: f.shortName ?? "",
        country: f.country ?? "",
        currency: f.currency ?? "",
        divisionId: f.division?.id ?? "",
      })}
      editTitle={(f) => `Edit factory: ${f.shortName || f.code || f.name}`}
      removeWarning={(f) =>
        `"${f.name}" will be permanently deleted. Projects using this factory will need to be reassigned.`
      }
      filterRow={(f, q) => {
        const s = q.toLowerCase();
        return (
          f.name.toLowerCase().includes(s) ||
          (f.code?.toLowerCase().includes(s) ?? false) ||
          (f.shortName?.toLowerCase().includes(s) ?? false) ||
          (f.country?.toLowerCase().includes(s) ?? false)
        );
      }}
      transformValues={(vals) => ({
        ...vals,
        divisionId: vals.divisionId === "" ? null : vals.divisionId,
      })}
    />
  );
}
