export const chatRoutes = {
  home: "/",
  questions: "/questions",
  knowledge: "/knowledge",
  usage: "/usage",
  settings: "/settings",
  chat: (id: number): string => `/chat/${id}`,
};

export const learnerRoutes = {
  home: "/",
  setup: "/setup",
  sources: "/sources",
  learning: "/learning",
  knowledge: "/knowledge",
};
// The address of the other app, for the cross-links on the login pages.
// Overridden per environment; the fallbacks are the local dev ports.
export const CHAT_APP_URL =
  import.meta.env.VITE_CHAT_APP_URL ?? "http://localhost:5173";
export const LEARNER_APP_URL =
  import.meta.env.VITE_LEARNER_APP_URL ?? "http://localhost:5174";

