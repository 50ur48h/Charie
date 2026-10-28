import { Outlet, useLocation, useParams } from "react-router";
import {
  AppShell,
  ChatSidebar,
  useChats,
  useStatus,
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
      <Outlet />
    </AppShell>
  );
}
