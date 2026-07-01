import { fileURLToPath } from "node:url";

import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// Build straight into the Python package so the SPA ships in the wheel and the
// qliff server serves it as static files. Relative base => works under any mount
// path. `do studio` just runs `npm run build` here.
export default defineConfig({
  plugins: [svelte()],
  base: "./",
  resolve: {
    alias: {
      $lib: fileURLToPath(new URL("./src/lib", import.meta.url)),
      // Cross-codebase toolkit shared with the docs explainers, kept at repo-root
      // shared/qui so both Svelte builds import one copy (colors, rng, palette).
      $shared: fileURLToPath(new URL("../shared/qui", import.meta.url)),
      // uplot (used by $shared/LinePlot) lives in studio/node_modules; the shared
      // dir has no node_modules of its own, so point bare `uplot` imports here.
      uplot: fileURLToPath(new URL("./node_modules/uplot", import.meta.url)),
    },
  },
  build: {
    outDir: "../qliff/server/static",
    emptyOutDir: true,
  },
  // In dev, proxy /api (REST + the /api/run WebSocket) through to the qliff
  // server so the SPA and the API share one origin -- same as production, where
  // the Python server serves both. No CORS, no cross-origin port juggling.
  // Override the backend with QLIFF_API (default: the cli.py default port).
  server: {
    port: 5174,
    proxy: {
      "/api": {
        target: process.env.QLIFF_API ?? "http://127.0.0.1:8731",
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
