import { Slider as SliderPrimitive } from "radix-ui";
import { forwardRef, type ComponentPropsWithoutRef, type ElementRef } from "react";
import { cn } from "./cn";

export interface SliderProps
  extends Omit<ComponentPropsWithoutRef<typeof SliderPrimitive.Root>, "value" | "defaultValue" | "onValueChange"> {
  value?: number;
  defaultValue?: number;
  onValueChange?: (value: number) => void;
}

const Slider = forwardRef<ElementRef<typeof SliderPrimitive.Root>, SliderProps>(
  ({ className, value, defaultValue, onValueChange, "aria-label": ariaLabel, ...props }, ref) => (
    <SliderPrimitive.Root
      ref={ref}
      value={value !== undefined ? [value] : undefined}
      defaultValue={defaultValue !== undefined ? [defaultValue] : undefined}
      onValueChange={onValueChange ? ([next]) => onValueChange(next) : undefined}
      className={cn(
        "relative flex touch-none select-none items-center disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    >
      <SliderPrimitive.Track className="relative h-1.5 grow overflow-hidden rounded-full bg-surface-2">
        <SliderPrimitive.Range className="absolute h-full bg-accent" />
      </SliderPrimitive.Track>
      <SliderPrimitive.Thumb
        aria-label={ariaLabel}
        className="block size-[18px] rounded-full border-2 border-accent bg-surface shadow-card focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      />
    </SliderPrimitive.Root>
  ),
);
Slider.displayName = SliderPrimitive.Root.displayName;

export { Slider };
