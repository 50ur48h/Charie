import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";

// Budget subset of settings (architecture 09 PATCH /api/settings). The full
// settings screen is P03.13; this covers the spending limits dialog only.
export interface BudgetSettings {
  spend_limit_usd: number;
  spend_warn_percent: number;
}

// GET /api/settings (budget fields). Other settings arrive in P03.13.
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
