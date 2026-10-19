import { redirect } from "next/navigation";
import { withCurrentUser } from "@/lib/current-user";
import { SecurityLogViewer } from "@/components/admin/security-log-viewer";
import { PageHeader } from "@/components/layout/page-header";

export default async function AuditLogPage() {
  return withCurrentUser(async (sessionUser) => {
    const permissions = sessionUser?.permissions ?? [];
    const isAdmin = sessionUser?.globalRole === "ADMIN";

    if (!isAdmin && !permissions.includes("VIEW_AUDIT_LOGS")) {
      redirect("/admin");
    }

    return (
      <>
        <PageHeader
          title="Audit Log"
          subtitle="Security & activity audit trail"
        />
        <SecurityLogViewer />
      </>
    );
  });
}
