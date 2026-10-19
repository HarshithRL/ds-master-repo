"use client";

import { useState, useCallback, useEffect } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";

interface ExpandableWidgetProps {
  children: React.ReactNode;
  title: string;
  headerRight?: React.ReactNode;
  className?: string;
}

export function ExpandableWidget({
  children,
  title,
  headerRight,
  className,
}: ExpandableWidgetProps) {
  const [expanded, setExpanded] = useState(false);

  const toggle = useCallback(() => setExpanded((v) => !v), []);

  useEffect(() => {
    if (!expanded) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setExpanded(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [expanded]);

  useEffect(() => {
    if (expanded) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => { document.body.style.overflow = ""; };
  }, [expanded]);

  const expandBtn = (
    <button
      onClick={toggle}
      className="rounded p-1 text-etex-gray-400 hover:text-etex-gray-600 dark:hover:text-gray-300 hover:bg-etex-gray-100 dark:hover:bg-[#282C34] transition-colors"
      title={expanded ? "Collapse" : "Expand"}
    >
      {expanded ? (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="4 14 10 14 10 20" />
          <polyline points="20 10 14 10 14 4" />
          <line x1="14" y1="10" x2="21" y2="3" />
          <line x1="3" y1="21" x2="10" y2="14" />
        </svg>
      ) : (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="15 3 21 3 21 9" />
          <polyline points="9 21 3 21 3 15" />
          <line x1="21" y1="3" x2="14" y2="10" />
          <line x1="3" y1="21" x2="10" y2="14" />
        </svg>
      )}
    </button>
  );

  /* ── Header bar — shared between section & compact ─────────── */
  const header = (
    <div className="flex items-center justify-between px-5 py-3 border-b border-(--border)">
      <div className="flex items-center gap-2.5">
        <span className="w-1 h-4 rounded-full bg-etex-orange" />
        <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-etex-gray-700 dark:text-gray-300">
          {title}
        </span>
      </div>
      <div className="flex items-center gap-2">
        {headerRight}
        {expandBtn}
      </div>
    </div>
  );

  // The expanded modal is rendered via portal to escape any transformed
  // ancestor (e.g. the dashboard's .animate-page-enter wrapper). A transform
  // creates a containing block, so without the portal `position: fixed`
  // anchors to that ancestor instead of the viewport.
  const modal = expanded && typeof document !== "undefined"
    ? createPortal(
        <>
          <div
            className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm animate-in fade-in duration-200"
            onClick={toggle}
          />
          {/* Centered dialog — capped at max-w-5xl so charts don't balloon
              on wide monitors. The viewport-relative w/h keeps it responsive. */}
          <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 pointer-events-none">
            <div className="pointer-events-auto bg-white dark:bg-[#1E2028] rounded-lg shadow-2xl overflow-hidden flex flex-col w-full max-w-5xl max-h-[90vh] animate-in zoom-in-95 fade-in duration-200">
              {header}
              <div className="flex-1 overflow-auto p-3 sm:p-4">
                {children}
              </div>
            </div>
          </div>
        </>,
        document.body,
      )
    : null;

  return (
    <>
      <div className={cn("card-compact", className)}>
        {header}
        {children}
      </div>
      {modal}
    </>
  );
}
