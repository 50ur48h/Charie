import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "./cn";

export function Card({ className, padded, ...props }: HTMLAttributes<HTMLDivElement> & { padded?: boolean }) {
  return (
    <div
      className={cn(
        "rounded-card border border-border bg-surface shadow-card",
        padded && "p-[20px_22px]",
        className,
      )}
      {...props}
    />
  );
}

export function CardHeader({
  title,
  sub,
  actions,
  className,
  ...props
}: HTMLAttributes<HTMLDivElement> & { title: ReactNode; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className={cn("mb-[14px] flex items-center gap-3", className)} {...props}>
      <div className="min-w-0 flex-1">
        <h3 className="card-title">{title}</h3>
        {sub && <p className="card-sub">{sub}</p>}
      </div>
      {actions}
    </div>
  );
}
