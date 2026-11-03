import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/utils";

interface CardProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  children: ReactNode;
  title?: string | undefined;
  subtitle?: string | undefined;
  action?: ReactNode | undefined;
  tone?: "raised" | "sunken" | undefined;
}

/** A soft surface with a hairline and a whisper of shadow (docs/design.md). */
export function Card({
  children,
  title,
  subtitle,
  action,
  tone = "raised",
  className,
  ...rest
}: CardProps) {
  return (
    <section
      data-slot="card"
      className={cn(
        "rounded-lg border p-5 sm:p-6",
        tone === "sunken"
          ? "border-transparent bg-surface-2"
          : "border-border bg-surface shadow-[0_1px_2px_rgba(var(--shadow-rgb),.05)]",
        className,
      )}
      {...rest}
    >
      {(title || action) && (
        <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            {title && (
              <h2 className="font-serif text-[17px] leading-snug font-semibold text-text">{title}</h2>
            )}
            {subtitle && <p className="mt-0.5 text-[13px] text-muted-foreground">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}
