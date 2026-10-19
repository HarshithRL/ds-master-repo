import { redirect } from "next/navigation";
import { withCurrentUser } from "@/lib/current-user";
import { UsersAdmin } from "@/components/admin/users-admin";

export default async function UsersAdminPage() {
  return withCurrentUser(async (sessionUser) => {
    const permissions = sessionUser?.permissions ?? [];
    const isAdmin = sessionUser?.globalRole === "ADMIN";

    if (!isAdmin && !permissions.includes("MANAGE_USERS")) {
      redirect("/admin/factories");
    }

    return <UsersAdmin />;
  });
}
