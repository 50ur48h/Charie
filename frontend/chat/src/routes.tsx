import type { RouteObject } from "react-router";
import { LoginPage, NotFoundPage, PlaceholderPage, RequireLogin } from "@charie/shared";
import { ChatLayout } from "./ChatLayout";
import { ChatPage } from "./pages/ChatPage";
import { NewChatPage } from "./pages/NewChatPage";
import { QuestionsPage } from "./pages/QuestionsPage";
import { KnowledgePage } from "./pages/KnowledgePage";
import { UsagePage } from "./pages/UsagePage";

const KIT_ENABLED = import.meta.env.DEV || import.meta.env.VITE_MOCK === "1";

export const routes: RouteObject[] = [
  {
    element: (
      <RequireLogin>
        <ChatLayout />
      </RequireLogin>
    ),
    children: [
      { index: true, element: <NewChatPage /> },
      { path: "chat/:chatId", element: <ChatPage /> },
      {
        path: "questions",
        element: <QuestionsPage />,
      },
      {
        path: "knowledge",
        element: <KnowledgePage />,
      },
      {
        path: "usage",
        element: <UsagePage />,
      },
      {
        path: "settings",
        element: (
          <PlaceholderPage
            app="chat"
            title="Settings"
            lead="Make Charie look and answer the way you like."
          />
        ),
      },
      { path: "*", element: <NotFoundPage app="chat" /> },
    ],
  },
  { path: "login", element: <LoginPage app="chat" /> },
  // Kit pages render outside the app frame: the frame demos bring their own.
  ...(KIT_ENABLED
    ? [
        {
          path: "__kit",
          lazy: () => import("./routes/__kit").then((m) => ({ Component: m.default })),
        },
        {
          path: "__kit/chat-frame",
          lazy: () =>
            import("./routes/__kit.chat-frame").then((m) => ({ Component: m.default })),
        },
        {
          path: "__kit/learner-frame",
          lazy: () =>
            import("./routes/__kit.learner-frame").then((m) => ({ Component: m.default })),
        },
      ]
    : []),
];
