import { redirect } from "next/navigation";
import { withCurrentUser } from "@/lib/current-user";
import { AppShell } from "@/components/layout/app-shell";

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  return withCurrentUser(async (sessionUser) => {
    if (!sessionUser) redirect("/access-denied");

    const user = {
      name: sessionUser.name || null,
      email: sessionUser.email || "",
      permissions: sessionUser.permissions ?? [],
      globalRole: sessionUser.globalRole ?? "MEMBER",
      image: sessionUser.image || null,
    };

    return <AppShell user={user}>{children}</AppShell>;
  });
}
