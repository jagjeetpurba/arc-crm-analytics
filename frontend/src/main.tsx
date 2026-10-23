import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./index.css";

const qc = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 5000 } } });
createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={qc}>
    <TooltipProvider>
      <App />
    </TooltipProvider>
  </QueryClientProvider>,
);
