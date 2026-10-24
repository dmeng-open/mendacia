import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const apiTarget = process.env.API_TARGET ?? `http://localhost:${process.env.API_PORT ?? "8000"}`;
const webPort = Number(process.env.WEB_PORT ?? "5173");

const proxy = {
  "/cases": { target: apiTarget },
  "/games": { target: apiTarget, ws: true },
  "/healthz": { target: apiTarget },
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: { port: webPort, strictPort: true, proxy },
  preview: { port: webPort, strictPort: true, proxy },
  test: { include: ["src/**/*.test.ts"], environment: "node" },
});
