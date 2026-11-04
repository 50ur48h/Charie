import type { Metadata, Viewport } from "next";

import "@fontsource-variable/inter";
import "@fontsource-variable/source-serif-4";
import "@fontsource-variable/jetbrains-mono";

import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SessionProvider } from "@/lib/auth/session";
import { PALETTE_STORAGE_KEY, THEME_STORAGE_KEY } from "@/lib/theme-keys";

import "./globals.css";

export const metadata: Metadata = {
  title: "Charie",
  description: "Ask your business data a question in plain English, and get an answer you can check.",
};

export const viewport: Viewport = {
  themeColor: "#f4f6f1",
};

/** Set the palette and light/dark before the first paint (D-046). */
const THEME_SCRIPT = `try{var d=document.documentElement,t=localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)}),p=localStorage.getItem(${JSON.stringify(PALETTE_STORAGE_KEY)});if(t==="dark"){d.setAttribute("data-theme","dark")}if(p&&p!=="sage"&&/^[a-z]+$/.test(p)){d.setAttribute("data-palette",p)}}catch(e){}`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // `suppressHydrationWarning` because the script above legitimately changes this element...
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <TooltipProvider delayDuration={300}>
          <SessionProvider>{children}</SessionProvider>
        </TooltipProvider>
        <Toaster />
      </body>
    </html>
  );
}
