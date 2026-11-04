"use client";

/** One session interface, two implementations behind it. */

import {
  PublicClientApplication,
  type AccountInfo,
  type IPublicClientApplication,
} from "@azure/msal-browser";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { authConfig, missingEntraSettings, type AuthConfig } from "./config";

// Without these the token carries no email or name.
const OIDC_SCOPES = ["openid", "profile", "email"];
import {
  DevTokenRefused,
  forgetDevSubject,
  mintDevToken,
  rememberDevSubject,
  rememberedDevSubject,
} from "./dev-tokens";

export interface Session {
  mode: AuthConfig["mode"];
  /** Who is signed in, or null. */
  who: string | null;
  /** Resolves a bearer token, or null when nobody is signed in. */
  getToken: () => Promise<string | null>;
  signIn: (subject?: string) => Promise<void>;
  signOut: () => Promise<void>;
  /** Configuration problems worth showing rather than hiding behind a redirect. */
  problems: string[];
  busy: boolean;
  error: string | null;
}

const SessionContext = createContext<Session | null>(null);

/** One MSAL instance per page, created outside React and initialized once. */
let msalInstance: PublicClientApplication | null = null;
let msalReady: Promise<IPublicClientApplication> | null = null;

function msalOnce(authority: string, clientId: string): Promise<IPublicClientApplication> {
  if (msalReady) return msalReady;
  msalInstance = new PublicClientApplication({
    auth: { authority, clientId, redirectUri: "/" },
    cache: { cacheLocation: "sessionStorage" },
  });
  const instance = msalInstance;
  msalReady = instance
    .initialize()
    // Must run before anything else touches the cache, and exactly once.
    .then(() => instance.handleRedirectPromise())
    .then(() => instance);
  return msalReady;
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) {
    throw new Error("useSession() must be used inside <SessionProvider>");
  }
  return session;
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const config = useMemo(() => authConfig(), []);
  const problems = useMemo(() => missingEntraSettings(config), [config]);

  const [who, setWho] = useState<string | null>(null);
  const [devToken, setDevToken] = useState<string | null>(null);
  const [msal, setMsal] = useState<IPublicClientApplication | null>(null);
  const [account, setAccount] = useState<AccountInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Restore a dev sign-in across reloads.
  useEffect(() => {
    if (config.mode !== "dev") return;
    const remembered = rememberedDevSubject();
    if (!remembered) return;
    mintDevToken(remembered)
      .then((identity) => {
        setDevToken(identity.token);
        setWho(identity.subject);
      })
      // Only a refusal makes the remembered subject worthless; an aborted or failed request.
      .catch((cause: unknown) => {
        if (cause instanceof DevTokenRefused) forgetDevSubject();
      });
  }, [config.mode]);

  useEffect(() => {
    if (config.mode !== "entra" || problems.length > 0) return;
    let cancelled = false;

    msalOnce(config.authority, config.clientId)
      .then((instance) => {
        if (cancelled) return;
        // Read the account after initialization has settled, not from the redirect result.
        const signedIn = instance.getActiveAccount() ?? instance.getAllAccounts()[0] ?? null;
        if (signedIn) instance.setActiveAccount(signedIn);
        setMsal(instance);
        setAccount(signedIn);
        setWho(signedIn?.username ?? signedIn?.name ?? null);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "Sign-in failed");
      });

    return () => {
      cancelled = true;
    };
  }, [config.mode, config.authority, config.clientId, problems.length]);

  const getToken = useCallback(async (): Promise<string | null> => {
    if (config.mode === "dev") return devToken;
    if (!msal || !account) return null;
    try {
      const result = await msal.acquireTokenSilent({
        scopes: [...OIDC_SCOPES, config.apiScope],
        account,
      });
      return result.accessToken;
    } catch {
      // A silent failure means interaction is required.
      await msal.acquireTokenRedirect({ scopes: [...OIDC_SCOPES, config.apiScope], account });
      return null;
    }
  }, [config.mode, config.apiScope, devToken, msal, account]);

  const signIn = useCallback(
    async (subject?: string) => {
      setError(null);
      setBusy(true);
      try {
        if (config.mode === "dev") {
          const identity = await mintDevToken(subject?.trim() || "dev-user");
          rememberDevSubject(identity.subject);
          setDevToken(identity.token);
          setWho(identity.subject);
          return;
        }
        if (!msal) throw new Error("Sign-in is still starting up. Try again in a moment.");
        await msal.loginRedirect({ scopes: [...OIDC_SCOPES, config.apiScope] });
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "Sign-in failed");
      } finally {
        setBusy(false);
      }
    },
    [config.mode, config.apiScope, msal],
  );

  const signOut = useCallback(async () => {
    if (config.mode === "dev") {
      forgetDevSubject();
      setDevToken(null);
      setWho(null);
      return;
    }
    await msal?.logoutRedirect();
  }, [config.mode, msal]);

  const value = useMemo<Session>(
    () => ({ mode: config.mode, who, getToken, signIn, signOut, problems, busy, error }),
    [config.mode, who, getToken, signIn, signOut, problems, busy, error],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
