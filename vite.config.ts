import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig(({ command }) => ({
  plugins: command === "serve" ? [react()] : [],
  ...(command === "build"
    ? { define: { "process.env.NODE_ENV": JSON.stringify("production") } }
    : {}),
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: process.env.PROMPTA_DEV_API_TARGET || "http://127.0.0.1:18765",
        changeOrigin: true,
      },
    },
  },
  build: {
    target: "es2022",
    outDir: "src/static",
    emptyOutDir: false,
    copyPublicDir: false,
    minify: false,
    lib: { entry: "src/ui/main.tsx", formats: ["es"], fileName: () => "app.js" },
    rollupOptions: { output: { codeSplitting: false } },
  },
}));
