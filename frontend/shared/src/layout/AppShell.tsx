import { useRef, useState } from "react";
import { Menu, PanelLeft } from "lucide-react";
import { IconButton } from "../components/Button";
import { Brand } from "./Logo";
import { MobileDrawer } from "./MobileDrawer";
import { chatRoutes, learnerRoutes } from "./appLinks";

export function AppShell({
  app,
  sidebar,
  sidebarHidden,
  onShowSidebar,
  children,
  logoHref,
}: {
  app: "chat" | "learner";
  sidebar: (place: "column" | "drawer") => React.ReactNode;
  sidebarHidden: boolean;
  onShowSidebar: () => void;
  children: React.ReactNode;
  logoHref?: string;
}) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const openerRef = useRef<HTMLButtonElement | null>(null);
  const home = logoHref ?? (app === "learner" ? learnerRoutes.setup : chatRoutes.home);
  return (
    <div
      className={
        sidebarHidden
          ? "app-shell grid h-dvh grid-cols-1"
          : "app-shell grid h-dvh grid-cols-[268px_1fr] max-[899px]:grid-cols-1"
      }
    >
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-[60] focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      {!sidebarHidden && (
        <aside className="min-h-0 bg-sidebar px-3 py-[14px] max-[899px]:hidden">
          {sidebar("column")}
        </aside>
      )}
      {sidebarHidden && (
        <IconButton
          label="Show sidebar"
          title="Show sidebar"
          onClick={onShowSidebar}
          className="fixed left-3 top-[11px] z-30 max-[899px]:hidden"
        >
          <PanelLeft />
        </IconButton>
      )}
      <div className="flex min-h-0 min-w-0 flex-col">
        <div className="mobile-topbar sticky top-0 z-20 hidden h-[54px] flex-none items-center border-b border-border-soft bg-bg px-5 print:hidden max-[899px]:flex">
          <MobileDrawer
            open={drawerOpen}
            onOpenChange={setDrawerOpen}
            trigger={
              <IconButton
                label="Open menu"
                title="Open menu"
                onClick={(e) => {
                  openerRef.current = e.currentTarget;
                }}
              >
                <Menu />
              </IconButton>
            }
            onExitComplete={() => openerRef.current?.focus({ preventScroll: true })}
          >
            {sidebar("drawer")}
          </MobileDrawer>
          <div className="mx-auto">
            <Brand app={app} markSize={24} href={home} />
          </div>
          <div className="w-8" aria-hidden="true" />
        </div>
        <main id="main" className="min-h-0 flex-1">
          <div className="h-full overflow-auto">{children}</div>
        </main>
      </div>
    </div>
  );
}
