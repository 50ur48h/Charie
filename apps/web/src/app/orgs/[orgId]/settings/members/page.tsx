"use client";

/**
 * Who belongs to this organization (WP13.1b). The screen gates its own
 * controls on the caller's role (B-008).
 */

import { Users } from "lucide-react";
import { use } from "react";

import { Members } from "@/components/screens/members";
import { Page, PageHeader } from "@/components/ui/page";
import { useOrgRole } from "@/lib/use-org-role";

export default function MembersPage({ params }: { params: Promise<{ orgId: string }> }) {
  const { orgId } = use(params);
  const { role } = useOrgRole(orgId);

  return (
    <Page>
      <PageHeader
        title="Members"
        subtitle="Who belongs here, and what they may do."
        icon={<Users />}
        back={{ href: `/orgs/${orgId}/settings`, label: "Back to settings" }}
      />
      <Members orgId={orgId} role={role} />
    </Page>
  );
}