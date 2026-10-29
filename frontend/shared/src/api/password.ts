import { useMutation } from "@tanstack/react-query";
import { apiFetch } from "./client";

// POST /api/password { current, new } (P05.4): a wrong current password gives
// 400 wrong_password, a short new one 400 password_too_short. Success keeps
// you signed in. The screen shows the API's message.
export function useChangePassword() {
  return useMutation({
    mutationFn: (passwords: { current: string; next: string }) =>
      apiFetch<{ ok: true }>("/api/password", {
        method: "POST",
        body: { current: passwords.current, new: passwords.next },
      }),
  });
}
