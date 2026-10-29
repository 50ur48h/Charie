import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { ApiError } from "./client";
import { loggedOutMe } from "./hooks";
import type { Me } from "./types";

export function createQueryClient(): QueryClient {
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({
      onError: (error) => expiredLogin(client, error),
    }),
    // Changes answer 401 the same way reads do: an expired settings save
    // or any other protected change returns you to /login. Sign-in
    // failures are already logged out, so their message still shows.
    mutationCache: new MutationCache({
      onError: (error) => expiredLogin(client, error),
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

function expiredLogin(client: QueryClient, error: unknown): void {
  // Any 401 means the login lapsed: drop cached data, mark logged out.
  if (error instanceof ApiError && error.status === 401) {
    client.clear();
    client.setQueryData<Me>(["me"], loggedOutMe());
  }
}
