import type { LucideIcon } from "lucide-react";
import { cn } from "./cn";

const iconTones = {
  accent: "bg-accent-soft text-accent-ink",
  good: "bg-good-soft text-good-ink",
  warn: "bg-warn-soft text-warn-ink",
  bad: "bg-bad-soft text-bad-ink",
  plain: "bg-surface-2 text-text-2",
} as const;

export type IconTone = keyof typeof iconTones;

export function IconBox({
  icon: Icon,
  tone = "accent",
  size = 36,
  className,
}: {
  icon: LucideIcon;
  tone?: IconTone;
  size?: number;
  className?: string;
}) {
  return (
    <span
      aria-hidden="true"
      style={{ width: size, height: size }}
      className={cn(
        "grid flex-none place-items-center rounded-[11px] bg-accent-soft text-accent-ink [--icon:18px]",
        iconTones[tone],
        className,
      )}
    >
      <Icon aria-hidden="true" />
    </span>
  );
}
