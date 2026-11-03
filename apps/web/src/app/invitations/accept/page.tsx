"use client";

import { Suspense } from "react";

import { AcceptInvite } from "@/components/screens/accept-invite";
import { EntryBrand, EntryFrame } from "@/components/screens/entry-frame";
import { SignIn } from "@/components/screens/sign-in";
import { useSession } from "@/lib/auth/session";

function Body() {
  const session = useSession();
  // Sign in first: an invitation adds *you*, so we have to know who you are.
  return session.who ? <AcceptInvite /> : <SignIn />;
}

export default function AcceptInvitationPage() {
  return (
    <EntryFrame>
      <div className="grid justify-items-center gap-6 text-center">
        <EntryBrand size="small" />
        <div className="grid gap-2">
          <h1 className="font-serif text-[28px] leading-tight font-semibold tracking-[-0.01em] text-text">
            Join an organization
          </h1>
          <p className="text-[14.5px] leading-relaxed text-pretty text-muted-foreground">
            Invitations are single-use and expire after seven days.
          </p>
        </div>
      </div>
      <Suspense fallback={null}>
        <Body />
      </Suspense>
    </EntryFrame>
  );
}
