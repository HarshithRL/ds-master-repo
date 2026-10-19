import { redirect } from "next/navigation";
import { withCurrentUser } from "@/lib/current-user";
import { CategoriesAdmin } from "@/components/admin/categories-admin";

export default async function CategoriesPage() {
  return withCurrentUser(async (sessionUser) => {
    const permissions = sessionUser?.permissions ?? [];
    const isAdmin = sessionUser?.globalRole === "ADMIN";

    if (!isAdmin && !permissions.includes("MANAGE_CATEGORIES")) {
      redirect("/admin");
    }

    return <CategoriesAdmin />;
  });
}
