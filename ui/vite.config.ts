import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";

const API_HOST = process.env.VITE_API_HOST ?? "localhost";
const API_PORT = process.env.VITE_API_PORT ?? "5000";
const DEV_PORT = parseInt(process.env.VITE_DEV_PORT ?? "5173", 10);

// Build output goes straight into the Python package so wheels ship the UI
// (see pyproject.toml [tool.hatch.build.targets.wheel] artifacts).
export default defineConfig({
  plugins: [tanstackRouter({ target: "react", autoCodeSplitting: true }), react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  build: {
    outDir: "../src/flowcept/webservice/ui_build",
    emptyOutDir: true,
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks: {
          echarts: ["echarts"],
          markdown: ["react-markdown", "remark-gfm"],
        },
      },
    },
  },
  server: {
    port: DEV_PORT,
    proxy: {
      "/api": { target: `http://${API_HOST}:${API_PORT}`, changeOrigin: true },
    },
  },
});
