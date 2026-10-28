import { Slot } from "radix-ui/Slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";
import { cn } from "./cn";

const buttonVariants = cva(
  "inline-flex h-[38px] cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-[11px] px-4 text-sm font-medium transition-[background-color,box-shadow,transform,color] duration-200 disabled:cursor-not-allowed disabled:opacity-50 [--icon:16px]",
  {
    variants: {
      variant: {
        primary:
          "bg-accent text-white shadow-button not-disabled:hover:-translate-y-px not-disabled:hover:bg-accent-hover",
        soft: "bg-accent-soft text-accent-ink not-disabled:hover:brightness-[.97]",
        outline:
          "border border-border bg-surface text-text-2 not-disabled:hover:border-focus not-disabled:hover:text-text",
        ghost: "text-muted not-disabled:hover:bg-[rgba(var(--shadow-rgb),.05)] not-disabled:hover:text-text",
        danger: "text-bad-ink not-disabled:hover:bg-bad-soft",
      },
      size: {
        sm: "h-8 rounded-[9px] px-3 text-[13px]",
        md: "",
        lg: "h-[46px] rounded-[13px] px-[22px] text-[15px]",
      },
      block: {
        true: "w-full",
        false: "",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
      block: false,
    },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export function Button({ variant, size, block, asChild, className, type = "button", ...props }: ButtonProps) {
  const Comp = asChild ? Slot : "button";
  return <Comp type={type} className={cn(buttonVariants({ variant, size, block }), className)} {...props} />;
}

export function IconButton({
  label,
  className,
  type = "button",
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      type={type}
      aria-label={label}
      title={label}
      className={cn(
        "inline-grid size-8 cursor-pointer place-items-center rounded-lg text-muted transition-[background-color,color] duration-150 not-disabled:hover:bg-surface-2 not-disabled:hover:text-text disabled:cursor-not-allowed disabled:opacity-50 [--icon:17px]",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}
