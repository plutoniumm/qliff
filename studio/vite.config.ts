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
    alias: { $lib: fileURLToPath(new URL("./src/lib", import.meta.url)) },
  },
  build: {
    outDir: "../qliff/server/static",
    emptyOutDir: true,
  },
  server: { port: 5174 },
});
