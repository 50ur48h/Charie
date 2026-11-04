"use client";

import { Toaster as Sonner, type ToasterProps } from "sonner";

/** Small confirmations ("Answer copied.") as a dark pill above the composer. */
export function Toaster(props: ToasterProps) {
  return (
    <Sonner
      position="bottom-center"
      offset={{ bottom: 112 }}
      mobileOffset={{ bottom: 96 }}
      gap={8}
      toastOptions={{
        style: {
          background: "rgba(20, 20, 22, 0.92)",
          color: "#ffffff",
          border: "none",
          borderRadius: "10px",
          boxShadow: "0 10px 30px rgba(0, 0, 0, 0.2)",
          fontFamily: "var(--font-sans)",
          fontSize: "13px",
          fontWeight: 500,
          padding: "10px 16px",
          width: "auto",
        },
      }}
      {...props}
    />
  );
}
