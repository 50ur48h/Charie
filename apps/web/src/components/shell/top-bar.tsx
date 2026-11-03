"use client";

import { Menu } from "lucide-react";
import type { ReactNode } from "react";

import { Hint } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

import { BrandMark } from "./brand";
import { useShell } from "./shell-context";

/**
 * The quiet bar across the top of the main column (design: `.topbar`).
 *
 * A centred title, actions on the right, and — on a small screen, where the
 * sidebar is a drawer — the button that opens it.
 */
export function TopBar({
  title,
  children,
  className,
  sticky = true,
}: {
  title?: ReactNode;
  /** Right-hand actions. */
  children?: ReactNode;
  className?: string | undefined;
  sticky?: boolean;
}) {
  const shell = useShell();
  return (
    <header
      className={cn(
        "z-20 flex h-[54px] shrink-0 items-center justify-center pr-12 pl-24 md:px-14",
        sticky && "sticky top-0 bg-background/85 backdrop-blur-md",
        className,
      )}
    >
      {shell && (
        <div className="absolute left-3 flex items-center gap-1 md:hidden">
          <Hint label="Menu">
            <button
              type="button"
              aria-label="Open navigation"
              onClick={shell.openNavigation}
              className="grid size-8 place-items-center rounded-sm text-muted-foreground hover:bg-surface-2 hover:text-text"
            >
              <Menu className="size-[18px]" aria-hidden="true" />
            </button>
          </Hint>
          <BrandMark className="size-6 text-brand" />
        </div>
      )}
      {title ? (
        <div className="min-w-0 truncate text-[14px] font-medium text-text-2">{title}</div>
      ) : null}
      {children ? <div className="absolute right-3 flex items-center gap-1">{children}</div> : null}
    </header>
  );
}

/** A small-screen-only top bar, for screens with no top bar of their own. */
export function MobileTopBar() {
  const shell = useShell();
  if (!shell) return null;
  return <TopBar className="md:hidden" />;
}
