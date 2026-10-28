import type { ChatGroup, SidebarUser } from "../layout/ChatSidebar";

export const FRAME_CHATS: ChatGroup[] = [
  {
    label: "Today",
    chats: [
      { id: 1, title: "How are we doing this month?" },
      { id: 2, title: "Top dishes by profit" },
    ],
  },
  {
    label: "Yesterday",
    chats: [
      { id: 3, title: "Why did delivery drop in Austin?" },
      { id: 4, title: "Weekend vs weekday sales" },
    ],
  },
  {
    label: "Previous 7 days",
    chats: [
      { id: 5, title: "Coupon impact in September" },
      { id: 6, title: "Food waste by restaurant" },
      { id: 7, title: "Best hours to add staff" },
      { id: 8, title: "Dallas vs Houston, last quarter" },
    ],
  },
];

export const FRAME_USER: SidebarUser = { name: "Sourabh", detail: "Bella Forno Group" };

export const FRAME_LEARNER_USER: SidebarUser = {
  name: "Sourabh",
  detail: "Owner · Bella Forno Group",
};

export const FRAME_QUESTION_COUNT = 3;
export const FRAME_NEW_SOURCES = 3;
export const FRAME_LEARNING_LIVE = true;
export const FRAME_REVIEW_COUNT = 4;

/** Obviously fake; the kit supplies it so no real address is needed. */
export const FRAME_CHAT_URL = "https://chat.example.invalid";
