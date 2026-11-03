"use client";

/**
 * The bootstrap screen on the front door: who you are, the organizations you
 * belong to, and the one place an organization can be created.
 *
 * It is every first login, so it says what to do next rather than presenting
 * an empty list.
 */

import { LogOut, Plus } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Notice } from "@/components/screens/entry-frame";
import { initials } from "@/components/shell/sidebar";
import { Badge, ROLE_TONES } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { SkeletonList } from "@/components/ui/skeleton";
import { createApi, type Me } from "@/lib/api-client";
import { emailIsUnknown, personLabel } from "@/lib/identity";
import { useSession } from "@/lib/auth/session";

/**
 * Who is signed in: an avatar, the best name we have for them, and the subject
 * the product actually authorizes against.
 */
export function Identity({ me, compact = false }: { me: Me; compact?: boolean }) {
  const name = me.name?.trim();
  const primary = name || (compact ? me.email?.split("@")[0] || me.subject : personLabel(me, me.subject));
  const secondary = !compact && name && me.email ? me.email : null;

  return (
    <div className="flex min-w-0 items-center gap-3.5">
      <span
        aria-hidden="true"
        className="grid size-11 shrink-0 place-items-center rounded-full bg-brand-soft text-[15px] font-semibold text-brand-ink"
      >
        {initials(me, me.subject)}
      </span>
      <div className="grid min-w-0 gap-0.5">
        <p className="truncate text-[15px] font-semibold text-text">{primary}</p>
        {secondary && <p className="truncate text-[13px] text-muted-foreground">{secondary}</p>}
        {!compact && <p className="flex min-w-0 items-center gap-1.5 text-[12.5px] text-muted-foreground">
          Subject
          <code className="truncate rounded-[6px] bg-surface-2 px-1.5 py-px text-[12px] text-text-2">
            {me.subject}
          </code>
        </p>}
        {/* Said once, quietly: a missing email claim is a configuration fact,
            not a fault of the person reading it. */}
        {!compact && emailIsUnknown(me) && (
          <p className="mt-1 text-[12.5px] leading-snug text-muted-foreground">
            Your sign-in did not include an email address, so we do not have one.
          </p>
        )}
      </div>
    </div>
  );
}

export function Profile() {
  const session = useSession();
  const api = useMemo(() => createApi(session.getToken), [session.getToken]);

  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [orgName, setOrgName] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setMe(await api.me());
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load your profile");
    }
  }, [api]);

  useEffect(() => {
    // Guarded so a slow response cannot write into an unmounted screen.
    let active = true;
    void (async () => {
      try {
        const next = await api.me();
        if (active) setMe(next);
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : "Could not load");
      }
    })();
    return () => {
      active = false;
    };
  }, [api]);

  const create = async () => {
    setBusy(true);
    try {
      await api.createOrg(orgName.trim());
      setOrgName("");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not create the organization");
    } finally {
      setBusy(false);
    }
  };

  const orgs = me?.memberships ?? [];

  return (
    <div className="grid gap-5">
      <header className="grid gap-2 text-center">
        <h1 className="font-serif text-[28px] leading-tight font-semibold tracking-[-0.01em] text-text">
          Welcome to Charie
        </h1>
        {/* Said only once we know: "you have none" while the answer is still
            in flight would be the empty-state-as-loading-state mistake. */}
        {me && (
          <p className="mx-auto max-w-[46ch] text-[14.5px] leading-relaxed text-pretty text-muted-foreground">
            {orgs.length === 0
              ? "You do not belong to an organization yet. Create one, or ask an admin to invite you."
              : "These are the organizations you belong to. You can create another below."}
          </p>
        )}
      </header>

      <Card tone="sunken" className="p-4 sm:p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          {me ? (
            <Identity me={me} compact />
          ) : (
            <div className="min-w-0 flex-1">
              <SkeletonList rows={1} avatar label="Loading your profile" />
            </div>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto"
            onClick={() => void session.signOut()}
          >
            <LogOut aria-hidden="true" />
            Sign out
          </Button>
        </div>
      </Card>

      {error && <Notice tone="bad">{error}</Notice>}

      {orgs.length > 0 && (
        <Card title="Your organizations">
          <ul className="-my-2 divide-y divide-border-soft">
            {orgs.map((membership) => (
              <li className="flex items-center gap-3 py-3" key={membership.org_id}>
                <span
                  aria-hidden="true"
                  className="grid size-9 shrink-0 place-items-center rounded-md bg-brand-soft font-serif text-[16px] font-semibold text-brand-ink"
                >
                  {membership.org_name.trim().charAt(0).toUpperCase() || "·"}
                </span>
                <p className="min-w-0 flex-1 truncate text-[14.5px] font-medium text-text">
                  {membership.org_name}
                </p>
                <Badge tone={ROLE_TONES[membership.role] ?? "neutral"} className="capitalize">
                  {membership.role}
                </Badge>
                {/* `/orgs/{id}` opens the organization: it redirects into its chat. */}
                <Button asChild size="sm">
                  <Link href={`/orgs/${membership.org_id}/settings`} role="button">
                    Set up
                  </Link>
                </Button>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title="Create an organization" subtitle="You become its first Admin.">
        <form
          className="flex flex-col gap-3 sm:flex-row sm:items-end"
          onSubmit={(event) => {
            event.preventDefault();
            void create();
          }}
        >
          <div className="min-w-0 flex-1">
            <Input
              label="Name"
              value={orgName}
              onChange={(event) => setOrgName(event.target.value)}
              placeholder="Acme"
              autoComplete="organization"
            />
          </div>
          <Button variant="primary" size="lg" type="submit" disabled={busy || !orgName.trim()}>
            <Plus aria-hidden="true" />
            {busy ? "Creating…" : "Create"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
