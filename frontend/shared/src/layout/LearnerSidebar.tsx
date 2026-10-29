import {
  ArrowUpRight,
  BookOpen,
  Brain,
  Database,
  ListChecks,
  MessageSquare,
  type LucideIcon,
} from "lucide-react";
import { RouterLink } from "./RouterLink";
import { Brand } from "./Logo";
import { learnerRoutes } from "./appLinks";
import {
  avatarClass,
  badgeClass,
  badgeSoftClass,
  liveDotClass,
  navIconClass,
  navLinkClass,
} from "./sidebarClasses";
import type { SidebarUser } from "./ChatSidebar";

export type LearnerSidebarPage = "setup" | "sources" | "learning" | "knowledge";

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

export function LearnerSidebar({
  active,
  newSources,
  learningLive,
  reviewCount,
  user,
  charieUrl,
}: {
  active: LearnerSidebarPage;
  newSources?: number;
  learningLive?: boolean;
  reviewCount?: number;
  user?: SidebarUser;
  charieUrl?: string;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col gap-1">
      <div className="flex items-center justify-between px-1 pb-2.5 pt-0.5">
        <Brand app="learner" href={learnerRoutes.setup} />
      </div>
      <nav className="grid gap-0.5" aria-label="Pages">
        <NavLink to={learnerRoutes.setup} icon={ListChecks} active={active === "setup"}>
          Setup guide
        </NavLink>
        <NavLink
          to={learnerRoutes.sources}
          icon={Database}
          active={active === "sources"}
          badge={
            newSources !== undefined && newSources > 0 ? (
              <span className={badgeSoftClass} aria-label={`${newSources} new documents`}>
                {newSources} new
              </span>
            ) : undefined
          }
        >
          Sources
        </NavLink>
        <NavLink
          to={learnerRoutes.learning}
          icon={Brain}
          active={active === "learning"}
          badge={
            learningLive ? (
              <span className={liveDotClass} title="Learning now" role="img" aria-label="Learning now" />
            ) : undefined
          }
        >
          Learning
        </NavLink>
        <NavLink
          to={learnerRoutes.knowledge}
          icon={BookOpen}
          active={active === "knowledge"}
          badge={
            reviewCount !== undefined && reviewCount > 0 ? (
              <span className={badgeClass} data-on-accent>
                {reviewCount}
                <span className="sr-only"> entries need review</span>
              </span>
            ) : undefined
          }
        >
          Knowledge
        </NavLink>
      </nav>
      <div className="flex-1" />
      <div className="grid gap-0.5 border-t border-border pt-2">
        {charieUrl !== undefined && (
          <a
            href={charieUrl}
            target="_blank"
            rel="noreferrer"
            className={navLinkClass(false)}
          >
            <MessageSquare aria-hidden="true" className={navIconClass(false)} />
            Open Charie
            <ArrowUpRight aria-hidden="true" className="ml-auto [--icon:17px] text-muted" />
          </a>
        )}
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
