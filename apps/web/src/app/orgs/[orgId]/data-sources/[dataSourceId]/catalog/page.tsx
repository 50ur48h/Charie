"use client";

import { Table2 } from "lucide-react";
import { use } from "react";

import { CatalogBrowser } from "@/components/screens/catalog";
import { SignIn } from "@/components/screens/sign-in";
import { Page, PageHeader } from "@/components/ui/page";
import { useSession } from "@/lib/auth/session";
import { useOrgRole } from "@/lib/use-org-role";

export default function CatalogPage({
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
        title="Catalog"
        subtitle="What this database holds, and what may be seen of it."
        icon={<Table2 />}
        back={{ href: `/orgs/${orgId}/data-sources`, label: "Back to data sources" }}
      />
      {session.who ? (
        <CatalogBrowser orgId={orgId} dataSourceId={dataSourceId} role={role} />
      ) : (
        <SignIn />
      )}
    </Page>
  );
}