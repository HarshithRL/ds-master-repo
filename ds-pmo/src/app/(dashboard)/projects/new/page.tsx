"use client";

import { useRouter } from "next/navigation";
import { ProjectForm } from "@/components/project/project-form";

export default function NewProjectPage() {
  const router = useRouter();

  return (
    <div className="bg-white border border-gray-200 rounded-sm p-6">
      <ProjectForm
        mode="create"
        onSuccess={(project) => router.push(`/projects/${project.id}`)}
        onCancel={() => router.push("/projects")}
      />
    </div>
  );
}
