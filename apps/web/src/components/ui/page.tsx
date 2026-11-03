import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { MobileTopBar } from "@/components/shell/top-bar";
import { cn } from "@/lib/utils";

/** The column every admin and account screen sits in. */
export function Page({
  children,
  wide = false,
  className,
}: {
  children: ReactNode;
  /** For screens with wide tables, such as the catalog. */
  wide?: boolean | undefined;
  className?: string | undefined;
}) {
  return (
    <>
      <MobileTopBar />
      <div
        className={cn(
          "mx-auto w-full animate-fade-up px-5 pt-6 pb-16 sm:px-8 sm:pt-10",
          wide ? "max-w-[1120px]" : "max-w-[880px]",
          className,
        )}
      >
        {children}
      </div>
    </>
  );
}

export function PageHeader({
  title,
  subtitle,
  action,
  back,
  icon,
}: {
  title: string;
  subtitle?: string | undefined;
  action?: ReactNode | undefined;
  /** A quiet way back to the parent screen, shown above the title. */
  back?: { href: string; label: string } | undefined;
  /** A small glyph beside the title. Decorative. */
  icon?: ReactNode | undefined;
}) {
  return (
    <header className="mb-7">
      {back && (
        <Link
          href={back.href}
          className="mb-3 inline-flex items-center gap-1.5 rounded-sm text-[13px] text-muted-foreground transition-colors hover:text-text"
        >
          <ArrowLeft aria-hidden="true" className="size-3.5" />
          {back.label}
        </Link>
      )}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          {icon && (
            <span
              aria-hidden="true"
              className="mt-0.5 grid size-10 shrink-0 place-items-center rounded-md bg-brand-soft text-brand-ink [&_svg]:size-5"
            >
              {icon}
            </span>
          )}
          <div className="min-w-0">
            <h1 className="font-serif text-[28px] leading-tight font-semibold tracking-[-0.01em] text-text">
              {title}
            </h1>
            {subtitle && (
              <p className="mt-1.5 max-w-[62ch] text-[14.5px] leading-relaxed text-muted-foreground">
                {subtitle}
              </p>
            )}
          </div>
        </div>
        {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
      </div>
    </header>
  );
}

export function Stack({ children }: { children: ReactNode }) {
  return <div className="grid gap-5">{children}</div>;
}

export function Row({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap items-center gap-2.5">{children}</div>;
}
