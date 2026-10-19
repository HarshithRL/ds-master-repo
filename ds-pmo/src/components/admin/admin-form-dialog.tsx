"use client";

/* ═══════════════════════════════════════════════════════════════════
   AdminFormDialog — shared modal shell for every admin form.

   Provides: header, body slot, error banner, cancel + submit footer.
   Used by users-admin, simple-crud-admin (factories/categories) and
   take-snapshots-dialog so all admin modals look and behave identically.
   ═══════════════════════════════════════════════════════════════════ */

import * as React from "react";
import { AlertTriangle, Loader2 } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

export interface AdminFormDialogProps {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
  onSubmit?: () => void;
  submitLabel?: string;
  cancelLabel?: string;
  submitting?: boolean;
  submitDisabled?: boolean;
  error?: string | null;
  /** Tailwind max-w-* class (default max-w-md). */
  maxWidth?: string;
  /** Custom footer (overrides default cancel/submit). */
  footer?: React.ReactNode;
}

export function AdminFormDialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  onSubmit,
  submitLabel = "Save",
  cancelLabel = "Cancel",
  submitting,
  submitDisabled,
  error,
  maxWidth = "max-w-md",
  footer,
}: AdminFormDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={`${maxWidth} rounded-md`}>
        <DialogHeader>
          <DialogTitle className="text-base font-semibold">{title}</DialogTitle>
          {description && (
            <p className="text-xs text-muted-foreground mt-1">{description}</p>
          )}
        </DialogHeader>

        <form
          onSubmit={
            onSubmit
              ? (e) => {
                  e.preventDefault();
                  onSubmit();
                }
              : undefined
          }
          className="space-y-4 py-1"
        >
          {children}

          {error && (
            <div className="flex items-start gap-2 p-2.5 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-800 rounded-sm text-xs text-red-700 dark:text-red-400">
              <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <DialogFooter className="pt-2">
            {footer ?? (
              <>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => onOpenChange(false)}
                  className="h-8 text-xs"
                  disabled={submitting}
                >
                  {cancelLabel}
                </Button>
                {onSubmit && (
                  <Button
                    type="submit"
                    size="sm"
                    disabled={submitDisabled || submitting}
                    className="bg-etex-orange hover:bg-etex-orange-dark text-white h-8 text-xs"
                  >
                    {submitting && (
                      <Loader2 className="w-3 h-3 mr-1.5 animate-spin" />
                    )}
                    {submitLabel}
                  </Button>
                )}
              </>
            )}
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
