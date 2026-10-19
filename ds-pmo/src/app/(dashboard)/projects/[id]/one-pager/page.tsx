import { Suspense } from "react";
import { ProjectOnePager } from "@/components/project/project-one-pager";
import { ProjectLoading } from "@/components/ui/page-state";

export default async function OnePagerPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <Suspense fallback={<ProjectLoading />}>
      <ProjectOnePager projectId={id} />
    </Suspense>
  );
}
