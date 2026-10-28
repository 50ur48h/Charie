import {
  BookOpen,
  Gauge,
  Inbox,
  PanelLeft,
  Settings,
  SquarePen,
  type LucideIcon,
} from "lucide-react";
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
  href,
  icon: Icon,
  active,
  badge,
  children,
}: {
  href: string;
  icon: LucideIcon;
  active?: boolean;
  badge?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <a href={href} className={navLinkClass(active)} aria-current={active ? "page" : undefined}>
      <Icon aria-hidden="true" className={navIconClass(active)} />
      {children}
      {badge}
    </a>
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
      <a
        href={chatRoutes.home}
        className="flex items-center gap-2.5 rounded-xl border border-border bg-surface px-3 py-2 text-sm font-medium shadow-card transition-[box-shadow,transform] duration-200 hover:-translate-y-px hover:shadow-lift"
      >
        <SquarePen aria-hidden="true" className="[--icon:17px] text-accent" />
        New chat
      </a>
      <nav className="mt-2 grid gap-0.5" aria-label="Pages">
        <NavLink
          href={chatRoutes.questions}
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
        <NavLink href={chatRoutes.knowledge} icon={BookOpen} active={active === "knowledge"}>
          Knowledge
        </NavLink>
      </nav>
      <div className="mt-2.5 grid flex-1 content-start gap-px overflow-auto" aria-label="Chats">
        {chats.status === "loading" &&
          Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="h-[30px] w-full" />)}
        {chats.status === "error" && (
          <div className="grid gap-2 px-3 py-2">
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
                    <a
                      key={chat.id}
                      href={chatRoutes.chat(chat.id)}
                      className={chatItemClass(isActive)}
                      aria-current={isActive ? "page" : undefined}
                    >
                      {chat.title}
                    </a>
                  );
                })}
              </div>
            ))
          ))}
      </div>
      <div className="grid gap-0.5 border-t border-border pt-2">
        <NavLink href={chatRoutes.usage} icon={Gauge} active={active === "usage"}>
          Usage
        </NavLink>
        <NavLink href={chatRoutes.settings} icon={Settings} active={active === "settings"}>
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
