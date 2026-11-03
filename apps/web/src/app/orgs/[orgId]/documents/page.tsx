"use client";

import { BookOpen } from "lucide-react";
import { use } from "react";

import { Documents } from "@/components/screens/documents";
import { SignIn } from "@/components/screens/sign-in";
import { Page, PageHeader } from "@/components/ui/page";
import { useSession } from "@/lib/auth/session";
import { useOrgRole } from "@/lib/use-org-role";

export default function DocumentsPage({ params }: { params: Promise<{ orgId: string }> }) {
  const { orgId } = use(params);
  const session = useSession();
  const { role } = useOrgRole(orgId);

  return (
    <Page>
      <PageHeader
        title="Knowledge"
        subtitle="What this organization has written down — the definitions, policies and notes Charie reads before it queries."
        icon={<BookOpen />}
      />
      {session.who ? <Documents orgId={orgId} role={role} /> : <SignIn />}
    </Page>
  );
}