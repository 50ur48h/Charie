import * as ProgressPrimitive from "radix-ui/Progress";
import { forwardRef, type ComponentPropsWithoutRef, type ElementRef } from "react";
import { cn } from "./cn";

const Progress = forwardRef<
  ElementRef<typeof ProgressPrimitive.Root>,
  ComponentPropsWithoutRef<typeof ProgressPrimitive.Root> & { label: string; thin?: boolean }
>(({ className, label, thin, value, max = 100, ...props }, ref) => (
  <ProgressPrimitive.Root
    ref={ref}
    aria-label={label}
    value={value}
    max={max}
    className={cn("h-2 overflow-hidden rounded-full bg-surface-2", thin && "h-[5px]", className)}
    {...props}
  >
    <ProgressPrimitive.Indicator
      className="block h-full rounded-[inherit] bg-accent transition-[width] duration-1000 ease-calm"
      style={{ width: `${Math.min(100, Math.max(0, ((value ?? 0) / max) * 100))}%` }}
    />
  </ProgressPrimitive.Root>
));
Progress.displayName = ProgressPrimitive.Root.displayName;

export { Progress };
