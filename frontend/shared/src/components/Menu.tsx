import { DropdownMenu as MenuPrimitive } from "radix-ui";
import { forwardRef, type ComponentPropsWithoutRef, type ElementRef } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "./cn";

const Menu = MenuPrimitive.Root;
const MenuTrigger = MenuPrimitive.Trigger;

const MenuContent = forwardRef<
  ElementRef<typeof MenuPrimitive.Content>,
  ComponentPropsWithoutRef<typeof MenuPrimitive.Content>
>(({ className, sideOffset = 6, align = "end", ...props }, ref) => (
  <MenuPrimitive.Portal>
    <MenuPrimitive.Content
      ref={ref}
      sideOffset={sideOffset}
      align={align}
      className={cn(
        "z-50 min-w-[200px] rounded-[12px] border border-border bg-surface p-1 shadow-pop",
        className,
      )}
      {...props}
    />
  </MenuPrimitive.Portal>
));
MenuContent.displayName = MenuPrimitive.Content.displayName;

const MenuItem = forwardRef<
  ElementRef<typeof MenuPrimitive.Item>,
  ComponentPropsWithoutRef<typeof MenuPrimitive.Item> & { icon?: LucideIcon; tone?: "default" | "danger" }
>(({ className, icon: Icon, tone = "default", children, ...props }, ref) => (
  <MenuPrimitive.Item
    ref={ref}
    className={cn(
      "flex h-[34px] cursor-pointer select-none items-center gap-2.5 rounded-[8px] px-3 text-sm text-text-2 outline-none data-[highlighted]:bg-[rgba(var(--shadow-rgb),.05)] data-[highlighted]:text-text [--icon:16px]",
      tone === "danger" && "text-bad-ink data-[highlighted]:bg-bad-soft",
      className,
    )}
    {...props}
  >
    {Icon && <Icon aria-hidden="true" className={tone === "danger" ? "text-bad-ink" : "text-muted"} />}
    {children}
  </MenuPrimitive.Item>
));
MenuItem.displayName = MenuPrimitive.Item.displayName;

const MenuSeparator = forwardRef<
  ElementRef<typeof MenuPrimitive.Separator>,
  ComponentPropsWithoutRef<typeof MenuPrimitive.Separator>
>(({ className, ...props }, ref) => (
  <MenuPrimitive.Separator ref={ref} className={cn("my-1 h-px bg-border", className)} {...props} />
));
MenuSeparator.displayName = MenuPrimitive.Separator.displayName;

export { Menu, MenuTrigger, MenuContent, MenuItem, MenuSeparator };
