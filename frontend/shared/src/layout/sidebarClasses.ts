// Tailwind copies of the design's sidebar classes (calm.css "App frame").
// Shared with the chat app ChatList so rows and labels match the sidebar.

export function navLinkClass(active?: boolean): string {
  return active
    ? "flex items-center gap-2.5 rounded-[10px] bg-surface px-3 py-2 text-sm font-medium text-text shadow-raised"
    : "flex items-center gap-2.5 rounded-[10px] px-3 py-2 text-sm text-text-2 hover:bg-[rgba(var(--shadow-rgb),.05)]";
}

export function navIconClass(active?: boolean): string {
  return active ? "[--icon:17px] text-accent" : "[--icon:17px] text-muted";
}

export const badgeClass =
  "ml-auto grid h-5 min-w-5 place-items-center rounded-full bg-accent px-1.5 text-[11.5px] font-semibold text-white";

export const badgeSoftClass =
  "ml-auto grid h-5 min-w-5 place-items-center rounded-full bg-accent-soft px-1.5 text-[11.5px] font-semibold text-accent-ink";

export const liveDotClass =
  "ml-auto size-2 rounded-full bg-good animate-[live_1.6s_ease-out_infinite]";

export const chatGroupClass =
  "mx-3 mb-1 mt-3.5 text-[11.5px] font-medium text-muted first:mt-1";

export function chatItemClass(active?: boolean): string {
  return active
    ? "block overflow-hidden text-ellipsis whitespace-nowrap rounded-[10px] bg-surface px-3 py-[7px] text-[13.5px] font-medium text-text shadow-raised"
    : "block overflow-hidden text-ellipsis whitespace-nowrap rounded-[10px] px-3 py-[7px] text-[13.5px] text-text-2 hover:bg-[rgba(var(--shadow-rgb),.05)]";
}

export const avatarClass =
  "grid size-[30px] flex-none place-items-center rounded-full bg-accent-soft text-[13px] font-semibold text-accent-ink";
