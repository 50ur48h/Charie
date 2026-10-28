import {
  BookOpen,
  Gauge,
  Inbox,
  PanelLeft,
  Settings,
  SquarePen,
  type LucideIcon,
} from "lucide-react";
import { RouterLink } from "./RouterLink";
import { Button, IconButton } from "../components/Button";
import { Skeleton } from "../components/Skeleton";
import { Brand } from "./Logo";
import { chatRoutes } from "./appLinks";
import {
  avatarClass,
  badgeClass,
  chatGroupClass,
  chatItemClass,
  navIconClass,
  navLinkClass,
} from "./sidebarClasses";

export type ChatSidebarPage = "questions" | "knowledge" | "usage" | "settings";

export interface ChatGroup {
  label?: string;
  chats: { id: number; title: string }[];
}

export type ChatListState =
  | { status: "loading" }
  | { status: "error"; onRetry: () => void }
  | { status: "ready"; groups: ChatGroup[] };

export interface SidebarUser {
  name: string;
  detail: string;
}

function NavLink({
  to,
  icon: Icon,
  active,
  badge,
  children,
}: {
  to: string;
  icon: LucideIcon;
  active?: boolean;
  badge?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <RouterLink to={to} className={navLinkClass(active)} aria-current={active ? "page" : undefined}>
      <Icon aria-hidden="true" className={navIconClass(active)} />
      {children}
      {badge}
    </RouterLink>
  );
}

export function ChatSidebar({
  active,
  activeChatId,
  chats,
  questionCount,
  user,
  onHide,
}: {
  active?: ChatSidebarPage;
  activeChatId?: number;
  chats: ChatListState;
  questionCount?: number;
  user?: SidebarUser;
  onHide?: () => void;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col gap-1">
      <div className="flex items-center justify-between px-1 pb-2.5 pt-0.5">
        <Brand app="chat" href={chatRoutes.home} />
        {onHide && (
          <IconButton label="Hide sidebar" title="Hide sidebar" onClick={onHide}>
            <PanelLeft />
          </IconButton>
        )}
      </div>
      <RouterLink
        to={chatRoutes.home}
        className="flex items-center gap-2.5 rounded-xl border border-border bg-surface px-3 py-2 text-sm font-medium shadow-card transition-[box-shadow,transform] duration-200 hover:-translate-y-px hover:shadow-lift"
      >
        <SquarePen aria-hidden="true" className="[--icon:17px] text-accent" />
        New chat
      </RouterLink>
      <nav className="mt-2 grid gap-0.5" aria-label="Pages">
        <NavLink
          to={chatRoutes.questions}
          icon={Inbox}
          active={active === "questions"}
          badge={
            questionCount !== undefined && questionCount > 0 ? (
              <span className={badgeClass}>
                {questionCount}
                <span className="sr-only"> waiting</span>
              </span>
            ) : undefined
          }
        >
          Questions for you
        </NavLink>
        <NavLink to={chatRoutes.knowledge} icon={BookOpen} active={active === "knowledge"}>
          Knowledge
        </NavLink>
      </nav>
      <div
        className="mt-2.5 grid flex-1 content-start gap-px overflow-auto"
        aria-label="Chats"
        data-testid="chat-list"
      >
        {chats.status === "loading" && (
          <div role="status" aria-label="Loading chats" className="grid content-start gap-px">
            {Array.from({ length: 5 }, (_, i) => (
              <Skeleton key={i} className="h-[30px] w-full" />
            ))}
          </div>
        )}
        {chats.status === "error" && (
          <div role="alert" className="grid gap-2 px-3 py-2">
            <p className="text-[13px] text-muted">Couldn&apos;t load your chats.</p>
            <Button variant="ghost" size="sm" onClick={chats.onRetry}>
              Try again
            </Button>
          </div>
        )}
        {chats.status === "ready" &&
          (chats.groups.length === 0 ? (
            <p className="px-3 py-2 text-[13px] text-muted">No chats yet.</p>
          ) : (
            chats.groups.map((group, gi) => (
              <div key={group.label ?? `group-${gi}`}>
                {group.label && <div className={chatGroupClass}>{group.label}</div>}
                {group.chats.map((chat) => {
                  const isActive = chat.id === activeChatId;
                  return (
                    <RouterLink
                      key={chat.id}
                      to={chatRoutes.chat(chat.id)}
                      className={chatItemClass(isActive)}
                      aria-current={isActive ? "page" : undefined}
                    >
                      {chat.title}
                    </RouterLink>
                  );
                })}
              </div>
            ))
          ))}
      </div>
      <div className="grid gap-0.5 border-t border-border pt-2">
        <NavLink to={chatRoutes.usage} icon={Gauge} active={active === "usage"}>
          Usage
        </NavLink>
        <NavLink to={chatRoutes.settings} icon={Settings} active={active === "settings"}>
          Settings
        </NavLink>
        {user && (
          <div className="flex items-center gap-2.5 px-2.5 pb-0.5 pt-2">
            <span className={avatarClass} aria-hidden="true">
              {user.name.charAt(0)}
            </span>
            <div>
              <div className="text-[13.5px] font-semibold">{user.name}</div>
              <div className="text-xs text-muted">{user.detail}</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
