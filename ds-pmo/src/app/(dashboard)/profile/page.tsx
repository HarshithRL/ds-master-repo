import { redirect } from "next/navigation";
import { withCurrentUser } from "@/lib/current-user";
import { fetchProfileData } from "@/lib/profile-data";
import { ProfileView } from "@/components/profile/profile-view";

export const dynamic = "force-dynamic";

export default async function ProfilePage() {
  return withCurrentUser(async (sessionUser) => {
    if (!sessionUser?.id) redirect("/access-denied");

    const data = await fetchProfileData(sessionUser.id);
    if (!data) redirect("/access-denied");

    return <ProfileView {...data} />;
  });
}
