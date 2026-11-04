/** Runtime auth configuration. */

export type AuthMode = "dev" | "entra";

export interface AuthConfig {
  mode: AuthMode;
  /** Entra only: the authority MSAL signs in against. */
  authority: string;
  clientId: string;
  /** The scope that yields an access token our API will accept. */
  apiScope: string;
}

/** Where this bundle is running, as far as the build knew. */
function buildEnvironment(): string {
  return process.env.NEXT_PUBLIC_ENV ?? "prod";
}

/** Dev sign-in is only ever legitimate where a dev issuer could exist. */
export function devSignInIsPermitted(): boolean {
  const where = buildEnvironment();
  return where === "local" || where === "ci";
}

/** Defaults to `entra`, and that direction is the whole point. */
export function authConfig(): AuthConfig {
  const requested = process.env.NEXT_PUBLIC_AUTH_MODE;
  const mode: AuthMode = requested === "dev" && devSignInIsPermitted() ? "dev" : "entra";
  return {
    mode,
    authority: process.env.NEXT_PUBLIC_ENTRA_AUTHORITY ?? "",
    clientId: process.env.NEXT_PUBLIC_ENTRA_CLIENT_ID ?? "",
    apiScope: process.env.NEXT_PUBLIC_API_SCOPE ?? "",
  };
}

/** Was dev sign-in asked for and refused? */
export function devSignInWasRefused(): boolean {
  return process.env.NEXT_PUBLIC_AUTH_MODE === "dev" && !devSignInIsPermitted();
}

/** Entra cannot work without all three; say so rather than failing at redirect. */
export function missingEntraSettings(config: AuthConfig): string[] {
  if (config.mode !== "entra") return [];
  return (
    [
      ["NEXT_PUBLIC_ENTRA_AUTHORITY", config.authority],
      ["NEXT_PUBLIC_ENTRA_CLIENT_ID", config.clientId],
      ["NEXT_PUBLIC_API_SCOPE", config.apiScope],
    ] as const
  )
    .filter(([, value]) => value.length === 0)
    .map(([name]) => name);
}
