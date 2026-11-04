"use client";

/** The app's home: an empty chat (WP13.1b). */

import { use } from "react";

import { ChatHome } from "@/components/screens/chat-home";

export default function ConversationsPage({ params }: { params: Promise<{ orgId: string }> }) {
  const { orgId } = use(params);
  return <ChatHome orgId={orgId} />;
}
