"use client";

import { BookMarked } from "lucide-react";
import { use } from "react";

import { Definitions } from "@/components/screens/definitions";
import { SignIn } from "@/components/screens/sign-in";
import { Page, PageHeader } from "@/components/ui/page";
import { useSession } from "@/lib/auth/session";
import { useOrgRole } from "@/lib/use-org-role";

export default function DefinitionsPage({
  params,
}: {
  params: Promise<{ orgId: string; dataSourceId: string }>;
}) {
  const { orgId, dataSourceId } = use(params);
  const session = useSession();
  const { role } = useOrgRole(orgId);

  return (
    <Page wide>
      <PageHeader
        title="Definitions"
        subtitle="What a metric means in this database — and which of those meanings Charie enforces on the queries it writes."
        icon={<BookMarked />}
        back={{ href: `/orgs/${orgId}/data-sources`, label: "Back to data sources" }}
      />
      {session.who ? (
        <Definitions orgId={orgId} dataSourceId={dataSourceId} role={role} />
      ) : (
        <SignIn />
      )}
    </Page>
  );
}