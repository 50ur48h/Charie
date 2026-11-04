"use client";

/** The frame every org screen sits in: the sidebar on the left, the page beside. */

import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { SignIn } from "@/components/screens/sign-in";
import { Page } from "@/components/ui/page";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { createApi, type Me } from "@/lib/api-client";
import { useSession } from "@/lib/auth/session";

import { ShellContext, type ShellState } from "./shell-context";
import { Sidebar } from "./sidebar";

export function AppShell({ orgId, children }: { orgId: string; children: ReactNode }) {
  const session = useSession();
  const pathname = usePathname();
  const api = useMemo(() => createApi(session.getToken), [session.getToken]);
  const [me, setMe] = useState<Me | null>(null);
  const [source, setSource] = useState<{ id: string; name: string } | null>(null);
  const [pending, setPending] = useState(0);
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    if (!session.who) return;
    let alive = true;
    void (async () => {
      try {
        const next = await api.me();
        if (alive) setMe(next);
      } catch {
        // The shell degrades to unnamed rather than blocking the page.
        if (alive) setMe(null);
      }
    })();
    return () => {
      alive = false;
    };
  }, [api, session.who]);

  useEffect(() => {
    if (!session.who) return;
    let alive = true;
    void (async () => {
      try {
        const active = await api.activeDataSource(orgId);
        if (!alive) return;
        setSource(
          active.data_source_id
            ? { id: active.data_source_id, name: active.data_source_name ?? "Your database" }
            : null,
        );
      } catch {
        if (alive) setSource(null);
      }
    })();
    return () => {
      alive = false;
    };
    // Re-read on navigation: choosing a source in Settings should show here.
  }, [api, orgId, session.who, pathname]);

  const membership = me?.memberships.find((entry) => entry.org_id === orgId) ?? null;
  const isAdmin = membership?.role === "admin";

  useEffect(() => {
    if (!isAdmin || !source) return;
    let alive = true;
    void (async () => {
      try {
        const proposals = await api.definitionProposals(orgId, source.id);
        if (alive) setPending(proposals.length);
      } catch {
        if (alive) setPending(0);
      }
    })();
    return () => {
      alive = false;
    };
  }, [api, orgId, source, isAdmin, pathname]);

  const person = me ? { email: me.email, name: me.name } : null;
  const questionsHref =
    isAdmin && source ? `/orgs/${orgId}/data-sources/${source.id}/definitions` : null;
  const pendingQuestions = questionsHref ? pending : 0;

  const state = useMemo<ShellState>(
    () => ({
      orgId,
      orgName: membership?.org_name ?? null,
      person,
      dataSource: source,
      pendingQuestions,
      openNavigation: () => setNavOpen(true),
    }),
    // `person` is rebuilt from `me` each render; key on `me` instead.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [orgId, membership?.org_name, me, source, pendingQuestions],
  );

  if (!session.who) {
    return (
      <main>
        <Page>
          <SignIn />
        </Page>
      </main>
    );
  }

  const sidebarProps = {
    orgId,
    orgName: membership?.org_name ?? null,
    person,
    pendingQuestions,
    questionsHref,
  };

  return (
    <ShellContext.Provider value={state}>
      <div className="flex h-dvh overflow-hidden bg-background">
        <aside className="hidden h-full shrink-0 md:block">
          <Sidebar {...sidebarProps} />
        </aside>
        <Sheet open={navOpen} onOpenChange={setNavOpen}>
          <SheetContent
            side="left"
            showCloseButton={false}
            className="w-[288px] max-w-[85vw] gap-0 border-r-0 bg-sidebar p-0"
          >
            <SheetTitle className="sr-only">Navigation</SheetTitle>
            <Sidebar {...sidebarProps} inSheet onNavigate={() => setNavOpen(false)} />
          </SheetContent>
        </Sheet>
        <main id="main" className="relative flex min-w-0 flex-1 flex-col overflow-y-auto">
          {children}
        </main>
      </div>
    </ShellContext.Provider>
  );
}
