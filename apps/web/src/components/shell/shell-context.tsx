"use client";

/** What the shell knows that the screens inside it may want: who you are. */

import { createContext, useContext } from "react";

import type { Named } from "@/lib/identity";

export interface ShellState {
  orgId: string;
  orgName: string | null;
  person: Named | null;
  /** The organization's active data source, when there is one. */
  dataSource: { id: string; name: string } | null;
  /** Imported definitions waiting for an Admin's answer. */
  pendingQuestions: number;
  openNavigation: () => void;
}

export const ShellContext = createContext<ShellState | null>(null);

export function useShell(): ShellState | null {
  return useContext(ShellContext);
}
