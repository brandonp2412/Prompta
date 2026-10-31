import { defineConfig } from "vite";

export default defineConfig({
  define: { "process.env.NODE_ENV": JSON.stringify("production") },
  build: {
    target: "es2022",
    outDir: "src/static",
    emptyOutDir: false,
    copyPublicDir: false,
    minify: false,
    lib: { entry: "src/ui/main.tsx", formats: ["es"], fileName: () => "app.js" },
    rollupOptions: { output: { codeSplitting: false } },
  },
});
