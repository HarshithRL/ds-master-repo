"use client";

import { UserSelector, type SelectedUser } from "@/components/ui/user-selector";
import { PropLabel } from "@/components/ui/auto-fields";

export type StakeholderRole = "SPONSOR" | "OWNER" | "PROJECT_MANAGER" | "PMO";

interface ProjectPeopleProps {
  sponsors: SelectedUser[];
  owners: SelectedUser[];
  pms: SelectedUser[];
  pmos: SelectedUser[];
  canEdit: boolean;
  onRoleChange: (role: StakeholderRole, users: SelectedUser[]) => void;
}

export function ProjectPeople({ sponsors, owners, pms, pmos, canEdit, onRoleChange }: ProjectPeopleProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-5 gap-y-3">
      <div>
        <PropLabel hint="Senior leader(s) who champion and fund the project">Sponsor(s)</PropLabel>
        <UserSelector
          mode="multi"
          value={sponsors}
          onChange={(users) => onRoleChange("SPONSOR", users)}
          placeholder="Select…"
          disabled={!canEdit}
        />
      </div>
      <div>
        <PropLabel hint="Business stakeholder(s) accountable for project outcomes">Owner(s)</PropLabel>
        <UserSelector
          mode="multi"
          value={owners}
          onChange={(users) => onRoleChange("OWNER", users)}
          placeholder="Select…"
          disabled={!canEdit}
        />
      </div>
      <div>
        <PropLabel hint="Person(s) responsible for day-to-day project execution">Project Manager(s)</PropLabel>
        <UserSelector
          mode="multi"
          value={pms}
          onChange={(users) => onRoleChange("PROJECT_MANAGER", users)}
          placeholder="Select…"
          requireEmail
          disabled={!canEdit}
        />
      </div>
      <div>
        <PropLabel hint="PMO contact(s) providing governance and reporting oversight">PMO(s)</PropLabel>
        <UserSelector
          mode="multi"
          value={pmos}
          onChange={(users) => onRoleChange("PMO", users)}
          placeholder="Select…"
          requireEmail
          disabled={!canEdit}
        />
      </div>
    </div>
  );
}
