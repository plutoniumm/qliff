// Headless smoke test for the built studio SPA. Serves qliff/server/static over
// a throwaway http server, drives the Builder in a real Chromium via puppeteer,
// and fails on any uncaught page error (e.g. Svelte's effect_update_depth_exceeded)
// or if selecting a code doesn't construct it on the canvas. This is the cheap
// guard for white-screen reactive loops that unit tests can't see.
//
// Run: node test/smoke.mjs   (after `npm run build`)

import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer";

const here = fileURLToPath(new URL(".", import.meta.url));
const STATIC_DIR = normalize(join(here, "..", "..", "qliff", "server", "static"));

const MIME = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".svg": "image/svg+xml",
};

// Static file server with an SPA fallback to index.html. /api/* returns 404 so
// the SPA's metadata fetches fail cleanly and fall back to their hardcoded lists.
function startServer() {
  const server = createServer(async (req, res) => {
    const url = (req.url ?? "/").split("?")[0];

    if (url.startsWith("/api/")) {
      res.writeHead(404);
      res.end("no api in smoke test");

      return;
    }

    const rel = url === "/" ? "index.html" : url.replace(/^\/+/, "");
    const path = normalize(join(STATIC_DIR, rel));

    try {
      const body = await readFile(path);
      res.writeHead(200, { "content-type": MIME[extname(path)] ?? "application/octet-stream" });
      res.end(body);
    } catch {
      const body = await readFile(join(STATIC_DIR, "index.html"));
      res.writeHead(200, { "content-type": "text/html" });
      res.end(body);
    }
  });

  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

function fail(msg) {
  console.error(`SMOKE FAIL: ${msg}`);
  process.exitCode = 1;
}

async function main() {
  const server = await startServer();
  const port = server.address().port;
  const url = `http://127.0.0.1:${port}/`;

  const browser = await puppeteer.launch({
    headless: "new",
    args: ["--no-sandbox"],
  });
  const page = await browser.newPage();

  const errors = [];
  page.on("pageerror", (err) => errors.push(String(err)));
  page.on("console", (msg) => {
    const text = msg.text();

    if (process.env.SMOKE_DEBUG) {
      console.log(`[console.${msg.type()}] ${text}`);
    }

    // 404s for /api/* are expected in this static harness (the SPA falls back to
    // its hardcoded metadata); only real script errors count.
    if (msg.type() === "error" && !text.includes("Failed to load resource")) {
      errors.push(text);
    }
  });

  try {
    await page.goto(url, { waitUntil: "networkidle0", timeout: 15000 });

    // Switch to the Builder tab (default view is Diagrams).
    await page.evaluate(() => {
      const tab = [...document.querySelectorAll("button.tab")].find(
        (b) => b.textContent?.trim() === "Builder",
      );
      tab?.click();
    });
    await page.waitForSelector("svg.canvas", { timeout: 5000 });

    // Select the repetition code in the Code dropdown (the select that carries a
    // "freeform" option) and let Svelte react.
    const codeSelector = await page.evaluate(() => {
      const sel = [...document.querySelectorAll("select")].find((s) =>
        [...s.options].some((o) => o.value === "freeform"),
      );

      if (!sel) {
        return null;
      }

      sel.id = "__smoke_code";

      return "#__smoke_code";
    });

    if (codeSelector === null) {
      fail("could not find the Code dropdown");
    } else {
      await page.select(codeSelector, "repetition");
      // give effects a couple of frames to flush
      await new Promise((r) => setTimeout(r, 400));

      const tiles = await page.evaluate(
        () => document.querySelectorAll("svg.canvas polygon.tile").length,
      );

      if (tiles <= 0) {
        fail("selecting 'repetition' did not construct any tiles on the canvas");
      } else {
        console.log(`OK: repetition d=3 drew ${tiles} tiles on the canvas`);
      }

      // bump the distance and confirm the canvas reseeds.
      await page.evaluate(() => {
        const inp = [...document.querySelectorAll('input[type="number"]')].find(
          (i) => i.previousSibling?.textContent?.includes("Distance") ||
            i.parentElement?.textContent?.includes("Distance"),
        );

        if (inp) {
          inp.value = "5";
          inp.dispatchEvent(new Event("input", { bubbles: true }));
          inp.dispatchEvent(new Event("change", { bubbles: true }));
        }
      });
      await new Promise((r) => setTimeout(r, 400));

      const tiles5 = await page.evaluate(
        () => document.querySelectorAll("svg.canvas polygon.tile").length,
      );

      if (tiles5 !== 5) {
        fail(`distance change to 5 should redraw 5 tiles, got ${tiles5}`);
      } else {
        console.log(`OK: repetition d=5 drew ${tiles5} tiles on the canvas`);
      }

      // a 2D family must construct a d*d patch (rotated surface, d=5 -> 25).
      await page.select(codeSelector, "rotated_surface");
      await new Promise((r) => setTimeout(r, 400));

      const surfTiles = await page.evaluate(
        () => document.querySelectorAll("svg.canvas polygon.tile").length,
      );

      if (surfTiles !== 25) {
        fail(`rotated_surface d=5 should draw 25 tiles, got ${surfTiles}`);
      } else {
        console.log(`OK: rotated_surface d=5 drew ${surfTiles} tiles on the canvas`);
      }

      // The surface families expose a stabiliser-pattern selector (the select
      // carrying an "xzzx" option). Switching to XZZX must not change the geometry
      // (Clifford-equivalent) or throw a reactive error.
      const variantSel = await page.evaluate(() => {
        const sel = [...document.querySelectorAll("select")].find((s) =>
          [...s.options].some((o) => o.value === "xzzx"),
        );

        if (!sel) {
          return null;
        }

        sel.id = "__smoke_variant";

        return "#__smoke_variant";
      });

      if (variantSel === null) {
        fail("rotated_surface did not expose the stabiliser-pattern selector");
      } else {
        await page.select(variantSel, "xzzx");
        await new Promise((r) => setTimeout(r, 400));

        const xzzxTiles = await page.evaluate(
          () => document.querySelectorAll("svg.canvas polygon.tile").length,
        );

        if (xzzxTiles !== 25) {
          fail(`xzzx variant should keep 25 tiles, got ${xzzxTiles}`);
        } else {
          console.log(`OK: xzzx variant kept ${xzzxTiles} tiles (Clifford-equivalent)`);
        }
      }
    }

    if (errors.length > 0) {
      fail(`${errors.length} console/page error(s):\n  - ${errors.join("\n  - ")}`);
    }
  } catch (err) {
    fail(`exception: ${String(err)}`);
  } finally {
    await browser.close();
    server.close();
  }

  if (process.exitCode === 1) {
    console.error("SMOKE: FAILED");
  } else {
    console.log("SMOKE: PASSED");
  }
}

main();
