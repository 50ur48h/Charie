import { Outlet, useLocation, useParams } from "react-router";
import {
  AppShell,
  ChatSidebar,
  useChats,
  useSidebarHidden,
  type ChatListState,
  type ChatSidebarPage,
} from "@charie/shared";

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
  const chats: ChatListState = chatsQuery.isPending
    ? { status: "loading" }
    : chatsQuery.isError
      ? { status: "error", onRetry: () => void chatsQuery.refetch() }
      : {
          status: "ready",
          groups:
            chatsQuery.data.length > 0
              ? [
                  {
                    chats: chatsQuery.data.map((chat) => ({
                      id: chat.id,
                      title: chat.title,
                    })),
                  },
                ]
              : [],
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
          chats={chats}
          onHide={place === "column" ? () => setHidden(true) : undefined}
        />
      )}
    >
      <Outlet />
    </AppShell>
  );
}
