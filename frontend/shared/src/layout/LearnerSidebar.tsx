import {
  ArrowUpRight,
  BookOpen,
  Brain,
  Database,
  ListChecks,
  MessageSquare,
  type LucideIcon,
} from "lucide-react";
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
    <div className="flex min-h-0 flex-col gap-1">
      <div className="flex items-center justify-between px-1 pb-2.5 pt-0.5">
        <Brand app="learner" href={learnerRoutes.setup} />
      </div>
      <nav className="grid gap-0.5" aria-label="Pages">
        <NavLink href={learnerRoutes.setup} icon={ListChecks} active={active === "setup"}>
          Setup guide
        </NavLink>
        <NavLink
          href={learnerRoutes.sources}
          icon={Database}
          active={active === "sources"}
          badge={
            newSources !== undefined && newSources > 0 ? (
              <span className={badgeSoftClass}>{newSources} new</span>
            ) : undefined
          }
        >
          Sources
        </NavLink>
        <NavLink
          href={learnerRoutes.learning}
          icon={Brain}
          active={active === "learning"}
          badge={
            learningLive ? (
              <span className={liveDotClass} title="Learning now">
                <span className="sr-only">Learning now</span>
              </span>
            ) : undefined
          }
        >
          Learning
        </NavLink>
        <NavLink
          href={learnerRoutes.knowledge}
          icon={BookOpen}
          active={active === "knowledge"}
          badge={
            reviewCount !== undefined && reviewCount > 0 ? (
              <span className={badgeClass}>
                {reviewCount}
                <span className="sr-only"> to review</span>
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
          <a href={charieUrl} className={navLinkClass(false)}>
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
