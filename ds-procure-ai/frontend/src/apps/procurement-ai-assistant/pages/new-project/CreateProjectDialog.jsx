import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";

import { createProject } from "./createProject";
import { GREET_TRIGGER, writeIntakeSeed } from "./intakeChat";
import { projectWorkspacePath } from "./paths";
import {
  EMPTY_BRIEF,
  WORKFLOW_ENTRY_POINTS,
  canCreateProject,
  createProjectPayload,
} from "./projectFormOptions";
import { useNextProjectCode } from "./useNextProjectCode";
import "./CreateProjectDialog.css";

const EMPTY_OPTION = "";

function CreateProjectDialog() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const { projectId, loadingProjectId, loadError } = useNextProjectCode(open);
  const [brief, setBrief] = useState(EMPTY_BRIEF);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    setBrief(EMPTY_BRIEF);
    setSubmitting(false);
    setError(null);
  }, [open]);

  const formError = error || loadError;
  const canCreate = canCreateProject({
    projectId,
    submitting,
    loadingProjectId,
  });

  function updateBrief(field, value) {
    setBrief((current) => ({ ...current, [field]: value }));
  }

  function handleOpenChange(nextOpen) {
    if (submitting && !nextOpen) {
      return;
    }
    setOpen(nextOpen);
  }

  async function handleCreate() {
    if (!canCreate) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const created = await createProject(
        createProjectPayload(projectId, brief),
      );
      setOpen(false);
      writeIntakeSeed(created.id, {
        messages: [],
        pendingMessage: GREET_TRIGGER,
      });
      navigate(projectWorkspacePath(created.id), {
        state: {
          intakeMessages: [],
          pendingMessage: GREET_TRIGGER,
        },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create project.");
      setSubmitting(false);
    }
  }

  return (
    <>
      <button
        className="primary-button"
        type="button"
        onClick={() => handleOpenChange(true)}
      >
        + New Project
      </button>
      <Dialog
        open={open}
        onOpenChange={handleOpenChange}
        disablePointerDismissal
      >
        <DialogContent
          className="create-project-dialog sm:max-w-md"
          showCloseButton={!submitting}
        >
        <Card className="create-project-card">
          <CardHeader>
            <span className="create-project-eyebrow">
              CREATE A SOURCING PROJECT
            </span>
            <DialogTitle>New project</DialogTitle>
            <DialogDescription>
              Project ID is assigned automatically. Name, category, and
              workflow can be filled now or later in the workspace.
            </DialogDescription>
          </CardHeader>

          <CardContent>
            <div className="create-project-fields">
              <label>
                <span>PROJECT ID</span>
                <input
                  value={loadingProjectId ? "Loading…" : projectId}
                  readOnly
                  disabled
                  aria-readonly="true"
                  className="create-project-readonly"
                />
              </label>

              <label>
                <span>PROJECT NAME</span>
                <input
                  value={brief.name}
                  onChange={(event) => updateBrief("name", event.target.value)}
                  placeholder="e.g. France — screw & fastener selection"
                  disabled={submitting}
                />
              </label>

              <label>
                <span>CATEGORY</span>
                <input
                  value={brief.category}
                  onChange={(event) =>
                    updateBrief("category", event.target.value)
                  }
                  placeholder="Fasteners / mechanical fixings"
                  disabled={submitting}
                />
              </label>

              <label>
                <span>WORKFLOW</span>
                <select
                  value={brief.workflowEntryPoint}
                  onChange={(event) =>
                    updateBrief("workflowEntryPoint", event.target.value)
                  }
                  disabled={submitting}
                >
                  <option value={EMPTY_OPTION}>Select workflow…</option>
                  {WORKFLOW_ENTRY_POINTS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            {formError ? (
              <p className="create-project-error">{formError}</p>
            ) : null}
          </CardContent>

          <CardFooter className="create-project-footer">
            <button
              className="secondary-button"
              type="button"
              disabled={submitting}
              onClick={() => handleOpenChange(false)}
            >
              Cancel
            </button>
            <button
              className="primary-button"
              type="button"
              disabled={!canCreate}
              onClick={handleCreate}
            >
              {submitting ? "Creating…" : "Create project"}
            </button>
          </CardFooter>
        </Card>
      </DialogContent>
    </Dialog>
    </>
  );
}

export default CreateProjectDialog;
