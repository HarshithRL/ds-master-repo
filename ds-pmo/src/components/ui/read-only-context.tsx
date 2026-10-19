"use client";

import { createContext, useContext } from "react";

const ReadOnlyContext = createContext(false);

export const ReadOnlyProvider = ReadOnlyContext.Provider;

export function useReadOnly() {
  return useContext(ReadOnlyContext);
}
