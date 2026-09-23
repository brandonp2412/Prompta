import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

export default defineConfig({
  plugins: [svelte()],
  build: {
    target: "es2022",
    outDir: "src/static",
    emptyOutDir: false,
    copyPublicDir: false,
    minify: false,
    lib: {
      entry: "src/ui/main.ts",
      formats: ["es"],
      fileName: () => "app.js",
    },
    rollupOptions: {
      output: {
        codeSplitting: false,
      },
    },
  },
});
