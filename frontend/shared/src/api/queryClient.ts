import { QueryCache, QueryClient } from "@tanstack/react-query";
import { ApiError } from "./client";
import { loggedOutMe } from "./hooks";
import type { Me } from "./types";

export function createQueryClient(): QueryClient {
  const client = new QueryClient({
    queryCache: new QueryCache({
      onError: (error) => {
        // Any query that answers 401 means the login lapsed everywhere.
        if (error instanceof ApiError && error.status === 401) {
          client.setQueryData<Me>(["me"], loggedOutMe());
        }
      },
    }),
    defaultOptions: {
      queries: {
        retry: 1,
        staleTime: 30_000,
        refetchOnWindowFocus: false,
      },
    },
  });
  return client;
}
