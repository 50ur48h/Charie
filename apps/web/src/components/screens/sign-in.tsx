"use client";

/** The sign-in card. It stands on its own, so the front door. */

import { ArrowRight } from "lucide-react";
import { useState } from "react";

import { Notice } from "@/components/screens/entry-frame";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { devSignInWasRefused } from "@/lib/auth/config";
import { useSession } from "@/lib/auth/session";

const card = "mx-auto w-full max-w-[400px] shadow-[0_10px_32px_rgba(var(--shadow-rgb),.08)]";

/** The name dev sign-in suggests; the one-command demo bakes in its prepared user. */
const SUGGESTED_SUBJECT = process.env.NEXT_PUBLIC_DEV_SUBJECT || "alice";

export function SignIn() {
  const session = useSession();
  const [subject, setSubject] = useState(SUGGESTED_SUBJECT);

  if (session.problems.length > 0) {
    return (
      <Card title="Sign-in is not configured" className={card}>
        <Notice tone="warn">
          Set {session.problems.join(", ")} and rebuild the web app. Entra sign-in cannot start
          without them.
        </Notice>
      </Card>
    );
  }

  if (session.mode === "entra") {
    return (
      <Card
        title="Sign in"
        subtitle="You will be redirected to your organization's sign-in page."
        className={card}
      >
        <div className="grid gap-3">
          <Button
            variant="primary"
            size="lg"
            className="w-full"
            onClick={() => void session.signIn()}
            disabled={session.busy}
          >
            {session.busy ? "Starting…" : "Sign in"}
            {!session.busy && <ArrowRight aria-hidden="true" />}
          </Button>
          {session.error && <Notice tone="bad">{session.error}</Notice>}
          {devSignInWasRefused() && (
            <Notice tone="warn">
              This build asked for development sign-in and was refused: it was not built for a
              local environment. Entra is being used instead.
            </Notice>
          )}
        </div>
      </Card>
    );
  }

  return (
    <Card className={card}>
      <header className="mb-5 grid gap-1">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-serif text-[19px] leading-snug font-semibold text-text">Sign in</h2>
          <Badge tone="peach">Development mode</Badge>
        </div>
        <p className="text-[13px] leading-relaxed text-muted-foreground">
          The API mints a token for whatever name you enter.
        </p>
      </header>
      <form
        className="grid gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void session.signIn(subject);
        }}
      >
        <Input
          label="Who are you"
          value={subject}
          onChange={(event) => setSubject(event.target.value)}
          placeholder={SUGGESTED_SUBJECT}
          autoComplete="off"
          spellCheck={false}
        />
        <Button
          variant="primary"
          size="lg"
          type="submit"
          className="w-full"
          disabled={session.busy || !subject.trim()}
        >
          {session.busy ? "Signing in…" : "Continue"}
          {!session.busy && <ArrowRight aria-hidden="true" />}
        </Button>
        {session.error && <Notice tone="bad">{session.error}</Notice>}
      </form>
    </Card>
  );
}
