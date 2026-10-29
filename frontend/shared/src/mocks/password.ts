// The sample password the fake API accepts in mock mode.
// It lives here and in the vite configs only: never in a production build.
// POST /api/password can change it (P05.4); changing it here would not sign
// out existing tests because the session is a separate flag.
export const SAMPLE_PASSWORD = "bella-forno";

const PASSWORD_KEY = "charie-mock-password";

// The password a fresh login accepts: the changed one, or the sample.
export function getMockPassword(): string {
  try {
    return localStorage.getItem(PASSWORD_KEY) ?? SAMPLE_PASSWORD;
  } catch {
    return SAMPLE_PASSWORD;
  }
}

export function setMockPassword(next: string): void {
  try {
    localStorage.setItem(PASSWORD_KEY, next);
  } catch {
    // Test-only state; ignore.
  }
}
