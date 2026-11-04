"use client";

/** Whether the rail is collapsed — shared by the rail and the page beside it. */

import { useSyncExternalStore } from "react";

import { createPersisted } from "@/lib/persisted";

export const COLLAPSED_KEY = "charie.sidebar-collapsed";

/** Stored as a string, because `createPersisted` deals in string enumerations. */
function isFlag(value: string): value is "0" | "1" {
  return value === "0" || value === "1";
}

const store = createPersisted<"0" | "1">(COLLAPSED_KEY, "0", isFlag);

export function useSidebarCollapsed(): [boolean, () => void] {
  const collapsed = useSyncExternalStore(store.subscribe, store.get, store.getServer) === "1";
  return [collapsed, () => store.set(collapsed ? "0" : "1")];
}
