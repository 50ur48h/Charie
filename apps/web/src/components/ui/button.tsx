import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/**
 * One primary action per view; everything else is quieter (docs/design.md).
 *
 * Accepts the product's own variant names (`primary`, `secondary`, `ghost`,
 * `danger`) and shadcn's (`default`, `outline`, `destructive`, `link`), so a
 * shadcn component dropped in from the registry composes without edits.
 */
export const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-md text-[13.5px] font-medium transition-[background-color,color,box-shadow,transform] outline-none select-none focus-visible:ring-[3px] focus-visible:ring-focus disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        primary: "bg-brand font-semibold text-on-brand shadow-[0_1px_2px_rgba(var(--shadow-rgb),.08)] hover:bg-brand-hover",
        default: "bg-brand font-semibold text-on-brand shadow-[0_1px_2px_rgba(var(--shadow-rgb),.08)] hover:bg-brand-hover",
        secondary: "border border-border bg-surface text-text shadow-[0_1px_2px_rgba(var(--shadow-rgb),.05)] hover:bg-surface-2",
        outline: "border border-border bg-surface text-text shadow-[0_1px_2px_rgba(var(--shadow-rgb),.05)] hover:bg-surface-2",
        ghost: "text-muted-foreground hover:bg-surface-2 hover:text-text",
        danger: "bg-bad font-semibold text-white hover:bg-bad-ink",
        destructive: "bg-bad font-semibold text-white hover:bg-bad-ink",
        soft: "bg-brand-soft font-semibold text-brand-ink hover:bg-focus",
        link: "h-auto px-0 text-brand-ink underline-offset-4 hover:underline",
      },
      size: {
        default: "h-[34px] px-3.5",
        sm: "h-8 rounded-sm px-2.5 text-[13px]",
        lg: "h-10 px-5 text-[14.5px]",
        icon: "size-8 rounded-sm",
        "icon-sm": "size-7 rounded-sm",
      },
    },
    defaultVariants: {
      variant: "secondary",
      size: "default",
    },
  },
);

type Variant = NonNullable<VariantProps<typeof buttonVariants>["variant"]>;
type Size = NonNullable<VariantProps<typeof buttonVariants>["size"]>;

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant | undefined;
  size?: Size | undefined;
  /** Render the child element (a link, say) with button styling. */
  asChild?: boolean | undefined;
}

export function Button({ variant, size, asChild = false, className, type, ...rest }: ButtonProps) {
  const classes = cn(buttonVariants({ variant, size }), className);
  if (asChild) return <Slot.Root data-slot="button" className={classes} {...rest} />;
  return <button data-slot="button" type={type ?? "button"} className={classes} {...rest} />;
}
