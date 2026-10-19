"use client";

import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AdminFormDialog } from "@/components/admin/admin-form-dialog";

const PERIOD_RE = /^\d{4}-(0[1-9]|1[0-2])$/;

export function TakeSnapshotsDialog({
  open,
  onOpenChange,
  onConfirm,
  taking,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onConfirm: (periodLabel: string) => void;
  taking: boolean;
}) {
  const defaultPeriod = new Date().toISOString().slice(0, 7);
  const [period, setPeriod] = useState(defaultPeriod);
  const [existingCount, setExistingCount] = useState<number | null>(null);
  const [checking, setChecking] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (open) {
      setPeriod(defaultPeriod);
      setExistingCount(null);
    }
  }, [open, defaultPeriod]);

  useEffect(() => {
    if (!open || !PERIOD_RE.test(period)) {
      setExistingCount(null);
      return;
    }

    setChecking(true);
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/admin/snapshots/count?period=${period}`, {
          signal: controller.signal,
        });
        if (!res.ok) throw new Error();
        const data = await res.json();
        setExistingCount(data.count);
      } catch (e) {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setExistingCount(null);
      } finally {
        if (!controller.signal.aborted) setChecking(false);
      }
    }, 300);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [open, period]);

  const valid = PERIOD_RE.test(period);
  const hasExisting = existingCount != null && existingCount > 0;

  return (
    <AdminFormDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Take All Snapshots"
      onSubmit={() => onConfirm(period)}
      submitLabel={hasExisting ? "Overwrite Snapshots" : "Take Snapshots"}
      submitDisabled={!valid || checking}
      submitting={taking}
      maxWidth="max-w-sm"
    >
      <div className="space-y-1.5">
        <Label htmlFor="snapshot-period" className="text-xs text-muted-foreground">
          Period
        </Label>
        <Input
          id="snapshot-period"
          type="month"
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
          max={defaultPeriod}
          min="2020-01"
          className="h-8 text-sm font-mono"
        />
      </div>

      {checking && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="w-3 h-3 animate-spin" />
          Checking existing snapshots...
        </div>
      )}

      {!checking && hasExisting && (
        <div className="flex items-start gap-2 rounded-md bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 p-2.5 text-xs text-amber-800 dark:text-amber-300">
          <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
          <span>
            <strong>{existingCount}</strong> snapshot
            {existingCount !== 1 ? "s" : ""} already exist for{" "}
            <strong>{period}</strong>. They will be overwritten.
          </span>
        </div>
      )}
    </AdminFormDialog>
  );
}
