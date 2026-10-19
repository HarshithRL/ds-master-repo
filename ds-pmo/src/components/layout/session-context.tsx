"use client";

import { createContext, useContext } from "react";

export interface SessionUser {
  name: string | null;
  email: string;
  permissions: string[];
  globalRole: string;
  image: string | null;
}

const SessionUserContext = createContext<SessionUser | null>(null);

export const SessionUserProvider = SessionUserContext.Provider;

export function useSessionUser(): SessionUser | null {
  return useContext(SessionUserContext);
}

export function useIsAdmin(): boolean {
  return useContext(SessionUserContext)?.globalRole === "ADMIN";
}
