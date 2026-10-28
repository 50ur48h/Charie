import type { RouteObject } from "react-router";
import { LoginPage, NotFoundPage, PlaceholderPage, RequireLogin } from "@charie/shared";
import { ChatLayout, ChatThreadPage, NewChatPage } from "./ChatLayout";

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
      { path: "chat/:chatId", element: <ChatThreadPage /> },
      {
        path: "questions",
        element: (
          <PlaceholderPage
            app="chat"
            title="Questions for you"
            lead="While learning, Charie found a few things only you can answer. Each takes under a minute. If you skip one, Charie uses the default shown and says so in its answers."
          />
        ),
      },
      {
        path: "knowledge",
        element: (
          <PlaceholderPage
            app="chat"
            title="Knowledge"
            lead="Everything Charie has learned about your business, and how sure it is about each thing."
          />
        ),
      },
      {
        path: "usage",
        element: (
          <PlaceholderPage
            app="chat"
            title="Usage"
            lead="What Charie's AI has cost this month. Every number here comes from the log of each AI call."
          />
        ),
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
