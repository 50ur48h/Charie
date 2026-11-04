"use client";

/** The organization's front door is the chat (WP13.1b). */

import { useRouter } from "next/navigation";
import { use, useEffect } from "react";

export default function OrgPage({ params }: { params: Promise<{ orgId: string }> }) {
  const { orgId } = use(params);
  const router = useRouter();

  useEffect(() => {
    router.replace(`/orgs/${orgId}/conversations`);
  }, [router, orgId]);

  return null;
}
