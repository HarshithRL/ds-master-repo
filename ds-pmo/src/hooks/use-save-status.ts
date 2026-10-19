"use client";

import { createContext, useContext } from "react";

/** Debounce window (ms) for all autosave flows — project-detail batched
 *  patch, useOptimisticRecord, useOptimisticList. Centralized so the feel
 *  stays consistent across the app. */
export const SAVE_DEBOUNCE_MS = 1200;

export type SaveStatus = "idle" | "saving" | "saved" | "error";

export type SaveActions = {
  saving: () => void;
  saved: () => void;
  saveFailed: () => void;
};

export const SaveStatusContext = createContext<SaveActions>({
  saving: () => {},
  saved: () => {},
  saveFailed: () => {},
});

export function useSaveStatus() {
  return useContext(SaveStatusContext);
}
