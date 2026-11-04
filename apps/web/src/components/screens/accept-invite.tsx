"use client";

import { ArrowRight, Check } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { Notice } from "@/components/screens/entry-frame";
import { Badge, ROLE_TONES } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { createApi } from "@/lib/api-client";
import { useSession } from "@/lib/auth/session";

interface Joined {
  orgId: string;
  orgName: string;
  role: string;
}

const card = "mx-auto w-full max-w-[440px] shadow-[0_10px_32px_rgba(var(--shadow-rgb),.08)]";

export function AcceptInvite() {
  const session = useSession();
  const api = useMemo(() => createApi(session.getToken), [session.getToken]);
  const params = useSearchParams();

  // Seeded from the link on first render rather than in an effect: the value is known immediately.
  const [token, setToken] = useState(() => params.get("token") ?? "");
  const [joined, setJoined] = useState<Joined | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const accept = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await api.acceptInvitation(token.trim());
      setJoined({ orgId: result.org_id, orgName: result.org_name, role: result.role });
    } catch (cause) {
      // The API answers every bad token identically on purpose — unknown.
      setError(cause instanceof Error ? cause.message : "That invitation could not be accepted");
    } finally {
      setBusy(false);
    }
  };

  if (joined) {
    return (
      <Card className={card}>
        <div className="flex animate-pop-in flex-col items-center gap-4 text-center">
          <span
            aria-hidden="true"
            className="grid size-12 place-items-center rounded-full bg-good-soft text-good-ink [&_svg]:size-6"
          >
            <Check strokeWidth={2.25} />
          </span>
          <div className="grid gap-1">
            <h2 className="font-serif text-[22px] leading-tight font-semibold text-text">
              {"You're in"}
            </h2>
            <p className="text-[14px] text-muted-foreground">You joined {joined.orgName}.</p>
          </div>
          <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
            Your role
            <Badge tone={ROLE_TONES[joined.role] ?? "neutral"} className="capitalize">
              {joined.role}
            </Badge>
          </p>
          <div className="mt-1 flex w-full flex-col gap-2 sm:flex-row">
            <Button asChild variant="primary" size="lg" className="min-w-0 flex-1">
              <Link href={`/orgs/${joined.orgId}`}>
                <span className="truncate">Go to {joined.orgName}</span>
                <ArrowRight aria-hidden="true" />
              </Link>
            </Button>
            <Button asChild size="lg">
              <Link href="/">Home</Link>
            </Button>
          </div>
        </div>
      </Card>
    );
  }

  return (
    <Card
      title="Accept an invitation"
      subtitle="Paste the invitation token you were sent, or follow the link from your invite."
      className={card}
    >
      <form
        className="grid gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void accept();
        }}
      >
        <Input
          label="Invitation token"
          className="font-mono text-[13px]"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          placeholder="Paste your token"
          autoComplete="off"
          spellCheck={false}
        />
        <Button
          variant="primary"
          size="lg"
          type="submit"
          className="w-full"
          disabled={busy || !token.trim()}
        >
          {busy ? "Joining…" : "Join"}
        </Button>
        {error && <Notice tone="bad">{error}</Notice>}
      </form>
      <p className="mt-5 border-t border-border-soft pt-4 text-[12.5px] leading-relaxed text-muted-foreground">
        Signed in as <span className="font-medium text-text-2">{session.who}</span>. An invitation
        is tied to an organization, not to an email address, so it will add whoever redeems it.
      </p>
    </Card>
  );
}
