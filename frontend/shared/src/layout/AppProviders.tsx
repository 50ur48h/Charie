import { useState } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "../components/Toast";
import { TooltipProvider } from "../components/Tooltip";
import { createQueryClient } from "../api/queryClient";

export function AppProviders({ children }: { children: React.ReactNode }) {
  const [client] = useState(createQueryClient);
  return (
    <QueryClientProvider client={client}>
      <TooltipProvider>
        {children}
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}
