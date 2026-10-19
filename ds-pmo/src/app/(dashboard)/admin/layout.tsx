import { redirect } from "next/navigation";
import { withCurrentUser } from "@/lib/current-user";
import { AdminSidebar } from "@/components/admin/admin-sidebar";

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  return withCurrentUser(async (sessionUser) => {
    const permissions = sessionUser?.permissions ?? [];
    const globalRole = sessionUser?.globalRole ?? "MEMBER";

    // Admin area is reachable if you hold any admin permission OR are an ADMIN.
    if (permissions.length === 0 && globalRole !== "ADMIN") {
      redirect("/dashboard");
    }

    return (
      <div className="space-y-6">
        <div className="flex flex-col lg:flex-row gap-6 items-start">
          <AdminSidebar permissions={permissions} isAdmin={globalRole === "ADMIN"} />
          <div className="flex-1 min-w-0 w-full">{children}</div>
        </div>
      </div>
    );
  });
}
