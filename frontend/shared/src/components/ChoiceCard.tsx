import { RadioGroup as RadioGroupPrimitive } from "radix-ui";
import { forwardRef, type ComponentPropsWithoutRef, type ElementRef } from "react";
import { cn } from "./cn";

const ChoiceGroup = forwardRef<
  ElementRef<typeof RadioGroupPrimitive.Root>,
  ComponentPropsWithoutRef<typeof RadioGroupPrimitive.Root>
>(({ className, ...props }, ref) => (
  <RadioGroupPrimitive.Root ref={ref} className={cn("grid gap-2.5", className)} {...props} />
));
ChoiceGroup.displayName = RadioGroupPrimitive.Root.displayName;

const ChoiceCard = forwardRef<
  ElementRef<typeof RadioGroupPrimitive.Item>,
  ComponentPropsWithoutRef<typeof RadioGroupPrimitive.Item> & {
    title: string;
    sub?: string;
    num?: string;
  }
>(({ className, title, sub, num, ...props }, ref) => (
  <RadioGroupPrimitive.Item
    ref={ref}
    className={cn(
      "group flex w-full cursor-pointer items-start gap-3 rounded-[14px] border-[1.5px] border-border bg-surface p-[14px_16px] text-left transition-[border-color,background-color,box-shadow] duration-200 not-disabled:hover:border-focus disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:border-accent data-[state=checked]:bg-[color-mix(in_srgb,var(--accent-soft)_45%,var(--surface))] data-[state=checked]:shadow-[0_0_0_3px_var(--accent-soft)]",
      className,
    )}
    {...props}
  >
    <span
      aria-hidden="true"
      className="mt-px grid size-5 flex-none place-items-center rounded-full border-2 border-muted-2 transition-[border-color] duration-200 group-data-[state=checked]:border-accent"
    >
      <span className="hidden size-2.5 rounded-full bg-accent group-data-[state=checked]:block" />
    </span>
    <span className="min-w-0 flex-1">
      <span className="block text-[14.5px] font-semibold text-text">{title}</span>
      {sub && <span className="mt-0.5 block text-[13px] text-muted">{sub}</span>}
    </span>
    {num && (
      <span className="whitespace-nowrap pl-3 font-prose text-[18px] font-semibold text-text">
        {num}
      </span>
    )}
  </RadioGroupPrimitive.Item>
));
ChoiceCard.displayName = "ChoiceCard";

export { ChoiceGroup, ChoiceCard };
