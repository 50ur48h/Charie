import { useState } from "react";
import { Outlet, useLocation, useParams } from "react-router";
import {
  AppShell,
  ChatSidebar,
  SpendingBanner,
  SpendingLimitsDialog,
  useBudgetSettings,
  useChats,
  useStatus,
  useUpdateBudgetSettings,
  useSidebarHidden,
  type ChatListState,
  type ChatSidebarPage,
} from "@charie/shared";
import { groupChats } from "./chat/groupChats";
import { ChatList } from "./chat/ChatList";

function pageFromPath(pathname: string): ChatSidebarPage | undefined {
  if (pathname.startsWith("/questions")) return "questions";
  if (pathname.startsWith("/knowledge")) return "knowledge";
  if (pathname.startsWith("/usage")) return "usage";
  if (pathname.startsWith("/settings")) return "settings";
  return undefined;
}

export function ChatLayout() {
  const [hidden, setHidden] = useSidebarHidden();
  const { chatId } = useParams();
  const { pathname } = useLocation();
  const chatsQuery = useChats();
  const statusQuery = useStatus();
  const budgetQuery = useBudgetSettings();
  const updateBudget = useUpdateBudgetSettings();
  const [managing, setManaging] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const spending = statusQuery.data?.spending ?? null;
  const chats: ChatListState = chatsQuery.isPending
    ? { status: "loading" }
    : chatsQuery.isError
      ? { status: "error", onRetry: () => void chatsQuery.refetch() }
      : {
          status: "ready",
          groups: groupChats(chatsQuery.data).map((group) => ({
            label: group.label,
            chats: group.chats.map((chat) => ({ id: chat.id, title: chat.title })),
          })),
        };
  return (
    <AppShell
      app="chat"
      sidebarHidden={hidden}
      onShowSidebar={() => setHidden(false)}
      sidebar={(place) => (
        <ChatSidebar
          active={pageFromPath(pathname)}
          activeChatId={chatId === undefined ? undefined : Number(chatId)}
          questionCount={statusQuery.data?.questions_waiting}
          chats={chats}
          renderChats={(groups, activeId) => (<ChatList groups={groups} activeChatId={activeId} />)}
          onHide={place === "column" ? () => setHidden(true) : undefined}
        />
      )}
    >
      {spending && spending.state !== "ok" && (
        <SpendingBanner spending={spending} onManage={() => {
          setSaveError(null);
          setManaging(true);
        }} />
      )}
      <Outlet />
      {managing && budgetQuery.data && (
        <SpendingLimitsDialog
          limitUsd={budgetQuery.data.spend_limit_usd}
          warnPercent={budgetQuery.data.spend_warn_percent}
          saving={updateBudget.isPending}
          serverError={saveError}
          onSave={(patch) => {
            setSaveError(null);
            updateBudget.mutate(patch, {
              onSuccess: () => setManaging(false),
              onError: (error) => setSaveError(error.message),
            });
          }}
          onClose={() => {
            setManaging(false);
            setSaveError(null);
          }}
        />
      )}
    </AppShell>
  );
}
