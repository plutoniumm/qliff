// Headless smoke test for the built docs site, focused on the interactive tutorial
// routes. Serves the VitePress build output (docs/.vitepress/dist, under the
// production base /qliff/) over a throwaway http server, then drives a real
// Chromium through every explainer route. Fails on any uncaught page error (e.g.
// Svelte's effect_update_depth_exceeded) or if a route renders no <h1>/<section> --
// the cheap guard against white-screen reactive loops and broken islands that unit
// tests can't see.
//
// Run: node test/smoke.mjs   (after `npm run build`, from docs/)

import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer";

const here = fileURLToPath(new URL(".", import.meta.url));
const DIST = normalize(join(here, "..", ".vitepress", "dist"));
const BASE = "/qliff/"; // config.mts base in production builds

const ROUTES = ["gates", "mwpm", "bp", "tn", "coherent", "noise", "ler"];

const MIME = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".png": "image/png",
  ".ico": "image/x-icon",
};

async function tryRead(path) {
  try {
    return await readFile(path);
  } catch {
    return null;
  }
}

function startServer() {
  const server = createServer(async (req, res) => {
    let url = decodeURIComponent((req.url ?? "/").split("?")[0].split("#")[0]);
    if (url.startsWith(BASE)) {
      url = "/" + url.slice(BASE.length);
    }
    const rel = url.replace(/^\/+/, "");

    // resolve in order: exact file, dir index, <rel>.html (VitePress default urls)
    const candidates = rel === ""
      ? ["index.html"]
      : [rel, join(rel, "index.html"), `${rel}.html`];

    for (const c of candidates) {
      const body = await tryRead(normalize(join(DIST, c)));
      if (body !== null) {
        res.writeHead(200, { "content-type": MIME[extname(c)] ?? "application/octet-stream" });
        res.end(body);
        return;
      }
    }

    res.writeHead(404, { "content-type": "text/plain" });
    res.end(`not found: ${rel}`);
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
  const base = `http://127.0.0.1:${port}${BASE}`;

  const browser = await puppeteer.launch({ headless: "new", args: ["--no-sandbox"] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 900 });

  const errors = [];
  page.on("pageerror", (err) => errors.push(String(err)));
  page.on("console", (msg) => {
    const text = msg.text();
    if (process.env.SMOKE_DEBUG) {
      console.log(`[console.${msg.type()}] ${text}`);
    }
    if (msg.type() === "error" && !text.includes("Failed to load resource")) {
      errors.push(text);
    }
  });

  try {
    // overview page first: it is a NATIVE VitePress home layout (hero + features),
    // so each explainer is a native .VPFeature card -- no island here.
    await page.goto(`${base}tutorials/`, { waitUntil: "networkidle0", timeout: 20000 });
    await page.waitForSelector(".VPFeature", { timeout: 12000 }).catch(() => {});
    const cards = await page.evaluate(() => document.querySelectorAll(".VPFeature").length);
    if (cards !== ROUTES.length) {
      fail(`overview should show ${ROUTES.length} explainer feature cards, got ${cards}`);
    } else {
      console.log(`OK: overview rendered ${cards} native feature cards`);
    }

    for (const id of ROUTES) {
      const before = errors.length;
      await page.goto(`${base}tutorials/${id}`, { waitUntil: "networkidle0", timeout: 20000 });
      // wait for the island to mount its article + at least one section
      await page.waitForSelector(".qtut .section", { timeout: 12000 }).catch(() => {});

      const info = await page.evaluate(() => {
        // the page title is server-rendered markdown (tutorials/<id>.md), so it
        // lives in VitePress' doc container, not inside the .qtut island.
        const h1 = document.querySelector(".VPDoc h1");
        const sections = document.querySelectorAll(".qtut .section").length;
        // VitePress native "on this page" outline
        const outline = document.querySelectorAll(".VPDocAsideOutline a.outline-link").length;
        return { title: h1?.textContent?.trim() ?? null, sections, outline };
      });

      if (!info.title) {
        fail(`route /tutorials/${id} rendered no <h1>`);
      } else if (info.sections < 1) {
        fail(`route /tutorials/${id} rendered no <Section> content`);
      } else if (errors.length > before) {
        fail(`route /tutorials/${id} produced console/page errors`);
      } else {
        console.log(`OK: /tutorials/${id} -- "${info.title}" (${info.sections} sections, ${info.outline} outline links)`);
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

  console.log(process.exitCode === 1 ? "SMOKE: FAILED" : "SMOKE: PASSED");
}

main();
