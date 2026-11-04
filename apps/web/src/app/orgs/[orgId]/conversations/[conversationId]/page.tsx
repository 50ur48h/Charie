"use client";

/** One thread (WP13.2). */

import { use } from "react";

import { ConversationThread } from "@/components/screens/conversation";

export default function ConversationPage({
  params,
}: {
  params: Promise<{ orgId: string; conversationId: string }>;
}) {
  const { orgId, conversationId } = use(params);
  return <ConversationThread orgId={orgId} conversationId={conversationId} />;
}
