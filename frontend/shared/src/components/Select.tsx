import { Select as SelectPrimitive } from "radix-ui";
import { Check, ChevronDown } from "lucide-react";

export interface SelectOption {
  value: string;
  label: string;
}

export function Select({
  options,
  value,
  onValueChange,
  placeholder,
  disabled,
  id,
}: {
  options: SelectOption[];
  value?: string;
  onValueChange?: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  id?: string;
}) {
  return (
    <SelectPrimitive.Root value={value} onValueChange={onValueChange} disabled={disabled}>
      <SelectPrimitive.Trigger
        id={id}
        aria-label={placeholder}
        className="flex h-[42px] w-full cursor-pointer items-center justify-between gap-2 rounded-[11px] border border-border bg-surface px-[14px] text-[14.5px] text-text outline-none transition-[border-color,box-shadow] duration-200 focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-soft)] focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 data-[placeholder]:text-placeholder"
      >
        <SelectPrimitive.Value placeholder={placeholder} />
        <SelectPrimitive.Icon asChild>
          <ChevronDown aria-hidden="true" className="text-muted [--icon:16px]" />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          align="end"
          sideOffset={6}
          position="popper"
          className="max-h-[240px] min-w-[200px] rounded-[12px] border border-border bg-surface shadow-pop"
        >
          <SelectPrimitive.Viewport className="p-1">
            {options.map((option) => (
              <SelectPrimitive.Item
                key={option.value}
                value={option.value}
                className="relative flex h-[34px] cursor-pointer select-none items-center rounded-[8px] px-3 pr-9 text-sm text-text-2 outline-none data-[highlighted]:bg-[rgba(var(--shadow-rgb),.05)] data-[highlighted]:text-text"
              >
                <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
                <SelectPrimitive.ItemIndicator className="absolute right-3 inline-flex items-center">
                  <Check aria-hidden="true" className="text-accent [--icon:16px]" />
                </SelectPrimitive.ItemIndicator>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}
