"use client";

/** The front door (WP13.1b). */

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ApiHealth } from "@/components/api-health";
import { EntryBrand, EntryFrame } from "@/components/screens/entry-frame";
import { Profile } from "@/components/screens/profile";
import { SignIn } from "@/components/screens/sign-in";
import { createApi } from "@/lib/api-client";
import { useSession } from "@/lib/auth/session";

export default function Home() {
  const session = useSession();
  const router = useRouter();
  const api = useMemo(() => createApi(session.getToken), [session.getToken]);

  // `null` is "we have not asked yet".
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (!session.who) return;
    let alive = true;
    void (async () => {
      try {
        const me = await api.me();
        const only = me.memberships.length === 1 ? me.memberships[0] : undefined;
        if (alive && only) {
          router.replace(`/orgs/${only.org_id}/conversations`);
          return;
        }
      } catch {
        // Fall through to the profile, which reports its own failure and still offers the one...
      }
      if (alive) setChecked(true);
    })();
    return () => {
      alive = false;
    };
  }, [api, router, session.who]);

  // The mark alone while we look, rather than a blank page — it claims nothing.
  if (session.who && !checked) {
    return (
      <EntryFrame>
        <EntryBrand />
      </EntryFrame>
    );
  }

  if (session.who) {
    return (
      <EntryFrame wide footer={<ApiHealth />}>
        <EntryBrand size="small" wordmark={false} />
        <Profile />
      </EntryFrame>
    );
  }

  return (
    <EntryFrame footer={<ApiHealth />}>
      <EntryBrand heading>
        <span className="sm:block">Ask your business data a question in plain English.</span>{" "}
        <span className="sm:block">Get an answer you can check.</span>
      </EntryBrand>
      <SignIn />
    </EntryFrame>
  );
}
