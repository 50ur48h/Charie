import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { ThemeKey } from "../theme/theme";

// Full settings shape (P05.5 GET /api/settings): every key with its default,
// except password_hash which never leaves the server. time_zone is null until
// the setup guide sets it; P03.13 shows no time-zone control by design.
export interface Settings {
  theme: ThemeKey;
  answer_length: "short" | "normal" | "detailed";
  number_format: "short" | "full";
  thinking_minutes: number;
  show_reading: boolean;
  memory_on: boolean;
  spend_limit_usd: number;
  spend_warn_percent: number;
  time_zone: string | null;
  strict_mode: boolean;
  setup_done: boolean;
}

// PATCH /api/settings takes any subset except setup_done (set by
// POST /api/setup/finish, P09.10) and password_hash (POST /api/password).
export type SettingsPatch = Partial<
  Omit<Settings, "setup_done">
>;

// Budget subset of settings (architecture 09 PATCH /api/settings). Kept for
// the Usage spending-limits dialog; the full settings screen is P03.13.
export interface BudgetSettings {
  spend_limit_usd: number;
  spend_warn_percent: number;
}

// GET /api/settings (the whole object; screens pick the fields they show).
export function useSettings() {
  return useQuery({
    queryKey: ["settings"],
    queryFn: ({ signal }) => apiFetch<Settings>("/api/settings", { signal }),
  });
}

// PATCH /api/settings. The server validates and saves all-or-nothing; on
// error the screen shows the API's message and keeps its old values.
export function useUpdateSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (patch: SettingsPatch) =>
      apiFetch<Settings>("/api/settings", { method: "PATCH", body: patch }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["settings"] });
      void client.invalidateQueries({ queryKey: ["me"] });
      void client.invalidateQueries({ queryKey: ["status"] });
      void client.invalidateQueries({ queryKey: ["usage"] });
    },
  });
}

// GET /api/settings (budget fields). Other settings arrived in P03.13.
export function useBudgetSettings() {
  return useQuery({
    queryKey: ["settings", "budget"],
    queryFn: ({ signal }) => apiFetch<BudgetSettings>("/api/settings", { signal }),
  });
}

// PATCH /api/settings { spend_limit_usd?, spend_warn_percent? }. The server
// validates; the screen shows its error message.
export function useUpdateBudgetSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (patch: Partial<BudgetSettings>) =>
      apiFetch<BudgetSettings>("/api/settings", { method: "PATCH", body: patch }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["settings"] });
      void client.invalidateQueries({ queryKey: ["status"] });
      void client.invalidateQueries({ queryKey: ["usage"] });
    },
  });
}
