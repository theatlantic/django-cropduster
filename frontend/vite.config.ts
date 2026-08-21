import { fileURLToPath } from "node:url";
import process from "node:process";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const outDir = fileURLToPath(
  new URL("../cropduster/static/cropduster/dist", import.meta.url),
);

const devPort = Number(process.env.CROPDUSTER_DEV_PORT ?? 5173);
const devOrigin = process.env.CROPDUSTER_DEV_ORIGIN;

export default defineConfig({
  plugins: [react()],
  // Django's staticfiles storage supplies the URL prefix.
  base: "",
  build: {
    license: { fileName: "LICENSES.txt" },
    outDir,
    emptyOutDir: true,
    target: "es2022",
    sourcemap: true,
    cssCodeSplit: false,
    // collectstatic cannot rewrite asset URLs inside the IIFE.
    assetsInlineLimit: 100_000,
    minify: "esbuild",
    rollupOptions: {
      input: fileURLToPath(new URL("src/entry.tsx", import.meta.url)),
      output: {
        format: "iife",
        // staticfiles cannot rewrite dynamic chunk paths, so use one fixed file.
        inlineDynamicImports: true,
        entryFileNames: "cropduster.js",
        chunkFileNames: "cropduster.js",
        assetFileNames: (assetInfo) =>
          assetInfo.names?.some((name) => name.endsWith(".css"))
            ? "cropduster.css"
            : "[name][extname]",
      },
    },
  },
  server: {
    port: devPort,
    strictPort: true,
    cors: true,
    ...(devOrigin ? { origin: devOrigin } : {}),
  },
});
