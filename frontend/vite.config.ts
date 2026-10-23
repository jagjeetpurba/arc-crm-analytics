import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// /api is proxied to the FastAPI backend so the same build works embedded in an ERP iFrame
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: { port: 5173, proxy: { "/api": { target: process.env.VITE_API ?? "http://localhost:8000", changeOrigin: true } } },
});
