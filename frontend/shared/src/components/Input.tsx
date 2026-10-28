import { cloneElement, isValidElement, useId, type InputHTMLAttributes, type ReactElement, type ReactNode } from "react";
import { CircleAlert, type LucideIcon } from "lucide-react";
import { cn } from "./cn";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  icon?: LucideIcon;
  end?: ReactNode;
  inputRef?: React.Ref<HTMLInputElement>;
}

export function Input({ icon: Icon, end, className, inputRef, ...props }: InputProps) {
  const input = (
    <input
      ref={inputRef}
      className={cn(
        "h-[42px] w-full rounded-[11px] border border-border bg-surface px-[14px] text-[14.5px] outline-none transition-[border-color,box-shadow] duration-200 placeholder:text-placeholder focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-soft)] focus-visible:outline-none aria-invalid:border-bad",
        Icon && "pl-[40px]",
        className,
      )}
      {...props}
    />
  );
  if (!Icon && !end) return input;
  return (
    <span className="relative block">
      {Icon && (
        <Icon
          aria-hidden="true"
          className="pointer-events-none absolute left-[13px] top-1/2 -translate-y-1/2 text-muted [--icon:17px]"
        />
      )}
      {input}
      {end && <span className="absolute right-1.5 top-1/2 -translate-y-1/2">{end}</span>}
    </span>
  );
}

export function Field({
  label,
  hint,
  error,
  htmlFor,
  children,
  className,
}: {
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  htmlFor?: string;
  children: ReactNode;
  className?: string;
}) {
  const errorId = useId();
  const described = isValidElement(children) && error
    ? cloneElement(children as ReactElement<{ "aria-describedby"?: string }>, {
        "aria-describedby": errorId,
      })
    : children;
  return (
    <div className={cn("grid content-start gap-1.5", className)}>
      <label htmlFor={htmlFor} className="field-label">
        {label}
      </label>
      {described}
      {error ? (
        <p id={errorId} role="alert" className="flex items-center gap-1 text-[12.5px] text-bad-ink [--icon:14px]">
          <CircleAlert aria-hidden="true" />
          {error}
        </p>
      ) : (
        hint && <p className="field-hint">{hint}</p>
      )}
    </div>
  );
}
