import { redirect } from "next/navigation";
import { withCurrentUser } from "@/lib/current-user";
import { SnapshotsAdmin } from "@/components/admin/snapshots-admin";
import { PageHeader } from "@/components/layout/page-header";

export default async function SnapshotsAdminPage() {
  return withCurrentUser(async (sessionUser) => {
    if (sessionUser?.globalRole !== "ADMIN") {
      redirect("/admin");
    }

    return (
      <>
        <PageHeader
          title="Snapshots"
          subtitle="Browse and inspect project snapshots across all projects"
        />
        <SnapshotsAdmin />
      </>
    );
  });
}
