import { HttpResponse } from "msw";

// Session guard shared by the chat and learner fake addresses (mock only).
// The sample password signs in through /api/login; everything except login
// and health needs the session flag.
export const SESSION_KEY = "charie-mock-session";

const NOT_LOGGED_IN = {
  error: "not_logged_in",
  message: "Please sign in again.",
};

function hasSession(): boolean {
  try {
    return localStorage.getItem(SESSION_KEY) === "1";
  } catch {
    return false;
  }
}

export function needSession(): Response | null {
  if (hasSession()) return null;
  return HttpResponse.json(NOT_LOGGED_IN, { status: 401 });
}
