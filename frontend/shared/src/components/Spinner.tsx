import { cn } from "./cn";

const spinnerClass =
  "inline-block size-[14px] animate-[spin_.8s_linear_infinite] rounded-full border-2 border-accent-soft border-t-accent";

export function Spinner({ label, className }: { label?: string; className?: string }) {
  if (label) {
    return <span role="status" aria-label={label} className={cn(spinnerClass, className)} />;
  }
  return <span aria-hidden="true" className={cn(spinnerClass, className)} />;
}
