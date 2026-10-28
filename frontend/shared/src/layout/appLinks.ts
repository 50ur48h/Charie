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
