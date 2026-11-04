/** Development sign-in: ask the API's dev issuer for a token. */

import { apiBaseUrl } from "@/lib/api-client";

const STORAGE_KEY = "charie.dev-subject";

export interface DevIdentity {
  subject: string;
  token: string;
}

/** The API answered and would not issue a token for this subject. */
export class DevTokenRefused extends Error {}

export async function mintDevToken(subject: string): Promise<DevIdentity> {
  const url = new URL(`${apiBaseUrl()}/dev/token`);
  url.searchParams.set("sub", subject);
  url.searchParams.set("email", `${subject}@example.com`);

  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new DevTokenRefused(
      "The API did not issue a development token. Is it running with AUTH_MODE=dev?",
    );
  }

  const body: unknown = await response.json();
  const token = (body as { access_token?: unknown }).access_token;
  if (typeof token !== "string") {
    throw new DevTokenRefused("The development token response was not in the expected shape");
  }
  return { subject, token };
}

export function rememberDevSubject(subject: string): void {
  window.localStorage.setItem(STORAGE_KEY, subject);
}

export function forgetDevSubject(): void {
  window.localStorage.removeItem(STORAGE_KEY);
}

export function rememberedDevSubject(): string | null {
  return window.localStorage.getItem(STORAGE_KEY);
}
