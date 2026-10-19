import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { withCurrentUser } from "@/lib/current-user";
import { fetchProfileData } from "@/lib/profile-data";
import { sessionHasPermission } from "@/lib/permissions";
import { ProfileView } from "@/components/profile/profile-view";
import { Button } from "@/components/ui/button";

export const dynamic = "force-dynamic";

export default async function AdminUserDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return withCurrentUser(async (sessionUser) => {
    if (!sessionUser?.id) redirect("/access-denied");

    // Same gate as the Users admin section — ADMIN role implicitly satisfies
    // MANAGE_USERS via sessionHasPermission.
    if (!sessionHasPermission(sessionUser, "MANAGE_USERS")) {
      redirect("/admin");
    }

    const { id } = await params;
    const data = await fetchProfileData(id);
    if (!data) notFound();

    const isSelf = data.user.id === sessionUser.id;

    return (
      <ProfileView
        {...data}
        title={data.user.name}
        subtitle={
          isSelf
            ? "Your account, access and recent activity"
            : "Account, access and recent activity"
        }
        headerActions={
          <Button asChild variant="outline" size="sm" className="h-8 text-xs">
            <Link href="/admin">
              <ArrowLeft className="w-3.5 h-3.5 mr-1.5" />
              Back to Users
            </Link>
          </Button>
        }
      />
    );
  });
}
