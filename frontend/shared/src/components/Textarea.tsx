import type { Ref, TextareaHTMLAttributes } from "react";
import { cn } from "./cn";

export function Textarea({
  className,
  ref,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement> & {
  ref?: Ref<HTMLTextAreaElement>;
}) {
  return (
    <textarea
      ref={ref}
      className={cn(
        "h-auto min-h-[80px] w-full resize-y rounded-[11px] border border-border bg-surface px-[14px] py-[11px] text-[14.5px] leading-normal outline-none transition-[border-color,box-shadow] duration-200 placeholder:text-placeholder focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-soft)] focus-visible:outline-none aria-invalid:border-bad",
        className,
      )}
      {...props}
    />
  );
}
