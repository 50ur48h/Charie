import { useMutation, useQuery } from "@tanstack/react-query";
import { ApiError, apiFetch } from "./client";
import type { KnowledgeDetailResponse, KnowledgeListResponse } from "../knowledge/types";
import { KIND_GROUPS, type KnowledgeGroup } from "../knowledge/groups";

export interface KnowledgeFilters {
  group?: KnowledgeGroup;
  q?: string;
  version?: number | "draft";
}

// GET /api/knowledge?kind=&q=&version= (architecture 09). The screens
// fetch the whole version once and filter on the screen (instant), so
// pages leave group and q empty; the addresses still filter for direct
// use. Returns the version, rows, whole-version counts and needs_review.
export function useKnowledge(filters: KnowledgeFilters = {}) {
  const { group = "all", q = "", version } = filters;
  const params = new URLSearchParams();
  if (group !== "all") {
    const kinds = KIND_GROUPS.find((entry) => entry.key === group)?.kinds ?? [];
    if (kinds.length > 0) params.set("kind", kinds.join(","));
  }
  if (q.trim() !== "") params.set("q", q.trim());
  if (version !== undefined) params.set("version", String(version));
  const query = params.toString();
  return useQuery({
    queryKey: ["knowledge", group, q.trim(), version ?? "published"],
    queryFn: ({ signal }) =>
      apiFetch<KnowledgeListResponse>(`/api/knowledge${query ? `?${query}` : ""}`, { signal }),
  });
}

// GET /api/knowledge/{key}?version= (architecture 09). Detail uses the
// stable entry key, never a list index.
export function useKnowledgeEntry(key: string | null, version?: number | "draft") {
  return useQuery({
    queryKey: ["knowledge-entry", key, version ?? "published"],
    queryFn: ({ signal }) => {
      if (key === null) throw new Error("No entry selected.");
      const query = version !== undefined ? `?version=${version}` : "";
      return apiFetch<KnowledgeDetailResponse>(`/api/knowledge/${key}${query}`, { signal });
    },
    enabled: key !== null,
    retry: (count, error) =>
      error instanceof ApiError && error.status === 404 ? false : count < 1,
  });
}

// POST /api/knowledge/{key}/suggest { text } (architecture 09, P12.2 shape).
// The suggestion goes to the learner; the published entry never rewrites.
export function useSuggestChange() {
  return useMutation({
    mutationFn: ({ entryKey, text }: { entryKey: string; text: string }) =>
      apiFetch<{ ok: true }>(`/api/knowledge/${entryKey}/suggest`, {
        method: "POST",
        body: { text },
      }),
  });
}
