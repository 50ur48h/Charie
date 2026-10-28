import { Toaster as SonnerToaster, toast as sonnerToast } from "sonner";

export function toast(message: string): void {
  sonnerToast(message);
}

export function Toaster() {
  return (
    <SonnerToaster
      position="bottom-center"
      offset="120px"
      duration={2400}
      toastOptions={{
        unstyled: true,
        classNames: {
          toast:
            "rounded-[10px] bg-code-bg px-4 py-2.5 text-code-ink text-[13px] font-medium shadow-pop",
        },
      }}
    />
  );
}
