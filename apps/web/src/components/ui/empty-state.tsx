/** A place nobody has filled yet — not a page that failed (docs/design.md). */

import type { ReactNode } from "react";

export function EmptyState({
  icon,
  title,
  children,
  action,
}: {
  /** A quiet glyph. Decorative — the title carries the meaning. */
  icon?: ReactNode;
  title: string;
  /** Why this is empty and what would fill it. */
  children: ReactNode;
  /** The one thing to do, or a line naming who can do it. */
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-4 rounded-lg border border-dashed border-border bg-surface/60 px-6 py-10 text-center">
      {icon && (
        <span
          aria-hidden="true"
          className="grid size-11 place-items-center rounded-full bg-brand-soft text-brand-ink [&_svg]:size-5"
        >
          {icon}
        </span>
      )}
      <div className="grid max-w-md gap-1">
        <p className="font-serif text-[17px] font-semibold text-text">{title}</p>
        <p className="text-[14px] leading-relaxed text-muted-foreground">{children}</p>
      </div>
      {action && <div className="text-[13.5px] text-muted-foreground">{action}</div>}
    </div>
  );
}
