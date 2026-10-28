import { Dialog as DialogPrimitive } from "radix-ui";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { X } from "lucide-react";
import { IconButton } from "../components/Button";

export function MobileDrawer({
  open,
  onOpenChange,
  trigger,
  onExitComplete,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  trigger: React.ReactNode;
  onExitComplete?: () => void;
  children: React.ReactNode;
}) {
  const reduceMotion = useReducedMotion();
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Trigger asChild>{trigger}</DialogPrimitive.Trigger>
      <AnimatePresence onExitComplete={onExitComplete}>
        {open && (
          <DialogPrimitive.Portal forceMount key="mobile-drawer">
            <DialogPrimitive.Overlay forceMount asChild>
              <motion.div
                className="fixed inset-0 z-50 bg-[rgba(var(--shadow-rgb),.28)]"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
              />
            </DialogPrimitive.Overlay>
            <DialogPrimitive.Content forceMount asChild>
              <motion.aside
                className="fixed left-0 top-0 z-50 h-dvh w-[300px] max-w-[85vw] overflow-auto bg-sidebar px-3 py-[14px] shadow-pop"
                initial={{ x: "-100%" }}
                animate={{ x: 0 }}
                exit={{ x: "-100%" }}
                transition={
                  reduceMotion
                    ? { duration: 0 }
                    : { duration: 0.25, ease: [0.2, 0.8, 0.2, 1] }
                }
                onClick={(e) => {
                  if ((e.target as HTMLElement).closest("a")) onOpenChange(false);
                }}
              >
                <DialogPrimitive.Title className="sr-only">Menu</DialogPrimitive.Title>
                <IconButton
                  label="Close menu"
                  title="Close menu"
                  onClick={() => onOpenChange(false)}
                  className="absolute right-3 top-3"
                >
                  <X />
                </IconButton>
                {children}
              </motion.aside>
            </DialogPrimitive.Content>
          </DialogPrimitive.Portal>
        )}
      </AnimatePresence>
    </DialogPrimitive.Root>
  );
}
