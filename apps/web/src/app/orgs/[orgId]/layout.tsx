"use client";

/** Every screen inside an organization sits in the chat shell (WP13.1b). */

import { use } from "react";

import { AppShell } from "@/components/shell/app-shell";

export default function OrgLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ orgId: string }>;
}) {
  const { orgId } = use(params);
  return <AppShell orgId={orgId}>{children}</AppShell>;
}
