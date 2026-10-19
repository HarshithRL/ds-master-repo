import { redirect } from "next/navigation";
import { withCurrentUser } from "@/lib/current-user";
import { FactoriesAdmin } from "@/components/admin/factories-admin";

export default async function FactoriesPage() {
  return withCurrentUser(async (sessionUser) => {
    const permissions = sessionUser?.permissions ?? [];
    const isAdmin = sessionUser?.globalRole === "ADMIN";

    if (!isAdmin && !permissions.includes("MANAGE_FACTORIES")) {
      redirect("/admin");
    }

    return <FactoriesAdmin />;
  });
}
