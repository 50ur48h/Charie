"use client";

import type { ReactNode } from "react";

import { Hint } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/**
 * A titled card for one picture or table in an answer (design: `.a-figure`).
 *
 * The actions are quiet until the figure is hovered or focused — always shown on
 * touch screens, where there is no hover.
 */
export function Figure({
  title,
  subtitle,
  actions,
  controls,
  children,
  className,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  /** Quiet until hover or focus: download, full screen, spec. */
  actions?: ReactNode;
  /** Always shown: a view switch, say. */
  controls?: ReactNode;
  children: ReactNode;
  className?: string | undefined;
}) {
  return (
    <figure
      className={cn(
        "group/fig m-0 min-w-0 animate-fade-up rounded-lg border border-border bg-surface px-[18px] pt-4 pb-3 font-sans shadow-[0_1px_2px_rgba(var(--shadow-rgb),.05)]",
        className,
      )}
    >
      {(title || actions || controls) && (
        <figcaption className="mb-2 flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
          <div className="min-w-0 flex-1 basis-[220px]">
            {title && (
              <div className="font-serif text-[17px] leading-snug font-semibold text-text">{title}</div>
            )}
            {subtitle && <div className="mt-0.5 text-[12.5px] text-muted-foreground">{subtitle}</div>}
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            {actions && (
              <div className="flex gap-0.5 transition-opacity md:opacity-0 md:group-focus-within/fig:opacity-100 md:group-hover/fig:opacity-100">
                {actions}
              </div>
            )}
            {controls}
          </div>
        </figcaption>
      )}
      {children}
    </figure>
  );
}

export function FigureAction({
  label,
  onClick,
  children,
  pressed,
}: {
  label: string;
  onClick: () => void;
  children: ReactNode;
  pressed?: boolean | undefined;
}) {
  return (
    <Hint label={label}>
      <button
        type="button"
        aria-label={label}
        aria-pressed={pressed}
        onClick={onClick}
        className={cn(
          "grid size-8 place-items-center rounded-sm text-muted-foreground transition-colors hover:bg-surface-2 hover:text-text [&_svg]:size-[17px]",
          pressed && "bg-surface-2 text-text",
        )}
      >
        {children}
      </button>
    </Hint>
  );
}
