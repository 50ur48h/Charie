import { useMe } from "@charie/shared";

// The chat app's address from GET /api/me (decision C005): null until it
// loads, so Open Charie only shows once the address is known. Never a
// build-time variable (pr-rules blocks VITE_ overrides and .env files).
export function useChatUrl(): string | null {
  const me = useMe();
  return me.data?.chat_url ?? null;
}
