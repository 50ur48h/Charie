"use client";

/** Which role the signed-in person holds in one organization. */

import { useEffect, useMemo, useState } from "react";

import { createApi } from "@/lib/api-client";
import { useSession } from "@/lib/auth/session";

export interface OrgRole {
  /** "admin" | "contributor" | "reader", or null while unknown. */
  role: string | null;
  loading: boolean;
}

export function useOrgRole(orgId: string): OrgRole {
  const session = useSession();
  const api = useMemo(() => createApi(session.getToken), [session.getToken]);

  const [role, setRole] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const me = await api.me();
        const membership = me.memberships.find((entry) => entry.org_id === orgId);
        if (active) setRole(membership?.role ?? null);
      } catch {
        // A failure here means the screen stays read-only.
        if (active) setRole(null);
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [api, orgId]);

  return { role, loading };
}
