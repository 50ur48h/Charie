import { ChevronDown } from "lucide-react";
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { useId } from "react";

import { cn } from "@/lib/utils";

/** The look every text control shares, for screens that build their own. */
export const controlClass =
  "h-10 w-full rounded-md border border-border bg-surface px-3 text-[14px] text-text shadow-[0_1px_2px_rgba(var(--shadow-rgb),.04)] outline-none transition-[border-color,box-shadow] placeholder:text-placeholder focus:border-brand focus:ring-[3px] focus:ring-brand-soft disabled:cursor-not-allowed disabled:opacity-60";

interface FieldProps {
  label: string;
  error?: string | undefined;
  children: (id: string) => ReactNode;
}

function Field({ label, error, children }: FieldProps) {
  const id = useId();
  return (
    <div className="grid gap-1.5">
      <label className="text-[13px] font-medium text-text-2" htmlFor={id}>
        {label}
      </label>
      {children(id)}
      {error && <p className="text-[12.5px] text-bad-ink">{error}</p>}
    </div>
  );
}

interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "id"> {
  label: string;
  error?: string | undefined;
}

export function Input({ label, error, className, ...rest }: InputProps) {
  return (
    <Field label={label} error={error}>
      {(id) => (
        <input
          id={id}
          aria-invalid={error ? true : undefined}
          className={cn(controlClass, error && "border-bad focus:ring-bad-soft", className)}
          {...rest}
        />
      )}
    </Field>
  );
}

interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "id"> {
  label: string;
  options: readonly string[];
}

export function Select({ label, options, className, ...rest }: SelectProps) {
  return (
    <Field label={label}>
      {(id) => (
        <div className="relative">
          <select
            id={id}
            className={cn(controlClass, "cursor-pointer appearance-none pr-9", className)}
            {...rest}
          >
            {options.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
          <ChevronDown
            aria-hidden="true"
            className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-muted-foreground"
          />
        </div>
      )}
    </Field>
  );
}
