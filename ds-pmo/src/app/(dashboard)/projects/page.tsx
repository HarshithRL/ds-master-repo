import { Suspense } from "react";
import { ProjectsList } from "@/components/project/projects-list";
import { ProjectTableLoading } from "@/components/ui/page-state";

export default async function ProjectsPage() {
  return (
    <Suspense fallback={<ProjectTableLoading />}>
      <ProjectsList />
    </Suspense>
  );
}
