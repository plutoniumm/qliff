// Interactivity gate for the built tutorial routes. Beyond smoke (does it render?),
// this DRIVES each page's real controls -- bumps every range slider and fires its
// input event, clicks the gate/toggle buttons, advances the scrubber -- and
// asserts the visualization actually changed (a signature hash of the island's
// SVG/canvas/text moved) with no page errors. Runs under two engines so we know
// the pages work in a real Chromium AND in lightpanda:
//
//   node test/interact.mjs chromium
//   node test/interact.mjs lightpanda   (spawns `lightpanda serve` + connects over CDP)
//
// All DOM work happens inside page.evaluate so the same assertions run on either
// engine regardless of which puppeteer convenience APIs each implements.

import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";
import puppeteer from "puppeteer";

const here = fileURLToPath(new URL(".", import.meta.url));
const DIST = normalize(join(here, "..", ".vitepress", "dist"));
const BASE = "/qliff/"; // config.mts base in production builds
const ALL_ROUTES = ["gates", "mwpm", "bp", "tn", "coherent", "noise", "ler"];
const ENGINE = process.argv[2] ?? "chromium";
// optional 3rd arg: comma-separated subset of routes (isolates flaky engines)
const ROUTES = process.argv[3] ? process.argv[3].split(",") : ALL_ROUTES;
const LP_PORT = 9333;

const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf", ".png": "image/png", ".ico": "image/x-icon" };

async function tryRead(p) {
  try { return await readFile(p); } catch { return null; }
}

function startServer() {
  const server = createServer(async (req, res) => {
    let url = decodeURIComponent((req.url ?? "/").split("?")[0].split("#")[0]);
    if (url.startsWith(BASE)) url = "/" + url.slice(BASE.length);
    const rel = url.replace(/^\/+/, "");
    const candidates = rel === "" ? ["index.html"] : [rel, join(rel, "index.html"), `${rel}.html`];
    for (const c of candidates) {
      const body = await tryRead(normalize(join(DIST, c)));
      if (body !== null) {
        res.writeHead(200, { "content-type": MIME[extname(c)] ?? "application/octet-stream" });
        res.end(body);
        return;
      }
    }
    res.writeHead(404);
    res.end("nf");
  });

  return new Promise((r) => server.listen(0, "127.0.0.1", () => r(server)));
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// --- in-page functions (must be self-contained: serialized & run in the browser) ---

function pageSignature() {
  const root = document.querySelector(".qtut") ?? document.body;
  let s = "";
  for (const svg of root.querySelectorAll("svg")) s += svg.outerHTML;
  for (const c of root.querySelectorAll("canvas")) {
    try { s += c.toDataURL().slice(0, 512); } catch { s += `${c.width}x${c.height}`; }
  }
  s += root.innerText ?? "";
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return { hash: h, len: s.length };
}

function countControls() {
  const root = document.querySelector(".qtut") ?? document.body;
  return {
    sliders: root.querySelectorAll("input[type=range]").length,
    checks: root.querySelectorAll("input[type=checkbox]").length,
    buttons: root.querySelectorAll("button").length,
  };
}

function bumpSliders() {
  const root = document.querySelector(".qtut") ?? document.body;
  let n = 0;
  for (const r of root.querySelectorAll("input[type=range]")) {
    const min = Number(r.min || 0), max = Number(r.max || 100), step = Number(r.step || 1) || 1, cur = Number(r.value);
    let v = cur + step * Math.max(1, Math.round((max - min) / step / 3));
    if (v > max) v = min;
    if (v === cur) v = cur === max ? min : max;
    r.value = String(v);
    r.dispatchEvent(new Event("input", { bubbles: true }));
    r.dispatchEvent(new Event("change", { bubbles: true }));
    n++;
  }
  return n;
}

function clickButtons() {
  const root = document.querySelector(".qtut") ?? document.body;
  let n = 0;
  for (const b of root.querySelectorAll("button")) {
    if (n >= 5) break;
    const label = (b.getAttribute("aria-label") ?? "") + b.textContent;
    if (/play|pause|reset/i.test(label) || b.disabled) continue;
    b.click();
    n++;
  }
  return n;
}

function advanceScrubber() {
  const root = document.querySelector(".qtut") ?? document.body;
  const next = [...root.querySelectorAll("button[aria-label='next'], .scrubber button")].find((b) => !b.disabled);
  if (next) { next.click(); return 1; }
  return 0;
}

// --- engine bring-up ---

async function getBrowser() {
  if (ENGINE === "chromium") {
    const browser = await puppeteer.launch({ headless: "new", args: ["--no-sandbox"] });
    return { browser, stop: async () => browser.close() };
  }
  if (ENGINE === "lightpanda") {
    const proc = spawn("lightpanda", ["serve", "--host", "127.0.0.1", "--port", String(LP_PORT)], { stdio: ["ignore", "ignore", "inherit"] });
    // poll for the CDP endpoint
    let ws = null;
    for (let i = 0; i < 50; i++) {
      await sleep(200);
      try {
        const r = await fetch(`http://127.0.0.1:${LP_PORT}/json/version`);
        if (r.ok) { ws = (await r.json()).webSocketDebuggerUrl ?? `ws://127.0.0.1:${LP_PORT}`; break; }
      } catch { /* not up yet */ }
    }
    if (!ws) { proc.kill("SIGKILL"); throw new Error("lightpanda CDP server never came up"); }
    const browser = await puppeteer.connect({ browserWSEndpoint: ws });
    return { browser, stop: async () => { try { await browser.disconnect(); } catch { /**/ } proc.kill("SIGKILL"); } };
  }
  throw new Error(`unknown engine ${ENGINE}`);
}

async function main() {
  const server = await startServer();
  const base = `http://127.0.0.1:${server.address().port}/`;
  const { browser, stop } = await getBrowser();
  const fails = [];

  console.log(`\n=== interactivity · ${ENGINE} ===`);
  for (const id of ROUTES) {
    const page = await browser.newPage();
    const errs = [];
    page.on("pageerror", (e) => errs.push(String(e)));
    page.on("console", (m) => { if (m.type() === "error" && !m.text().includes("Failed to load resource")) errs.push(m.text()); });
    try {
      await page.goto(`${base}${BASE.replace(/^\//, "")}tutorials/${id}`, { waitUntil: "domcontentloaded", timeout: 25000 });
      await page.waitForSelector(".qtut .section", { timeout: 12000 }).catch(() => {});
      await sleep(400);

      const ctrl = await page.evaluate(countControls);
      const sig0 = await page.evaluate(pageSignature);

      const moved = [];
      const ns = await page.evaluate(bumpSliders); await sleep(250);
      let sig = await page.evaluate(pageSignature);
      if (sig.hash !== sig0.hash) moved.push(`sliders(${ns})`);

      const nb = await page.evaluate(clickButtons); await sleep(250);
      let sig2 = await page.evaluate(pageSignature);
      if (sig2.hash !== sig.hash) moved.push(`buttons(${nb})`);

      const nx = await page.evaluate(advanceScrubber); await sleep(250);
      const sig3 = await page.evaluate(pageSignature);
      if (nx && sig3.hash !== sig2.hash) moved.push("scrubber");

      const rendered = sig0.len > 0;
      const reacted = sig3.hash !== sig0.hash;
      const ok = rendered && reacted && errs.length === 0;
      if (!rendered) fails.push(`${id}: rendered nothing (sig len 0)`);
      else if (!reacted) fails.push(`${id}: no DOM change after driving ${ctrl.sliders} sliders / ${ctrl.buttons} buttons`);
      if (errs.length) fails.push(`${id}: ${errs.length} error(s): ${errs.slice(0, 2).join(" | ")}`);

      console.log(`${ok ? "OK " : "XX "} ${id.padEnd(9)} controls[s:${ctrl.sliders} c:${ctrl.checks} b:${ctrl.buttons}]  reacted via ${moved.join(", ") || "—"}${errs.length ? `  ERRORS:${errs.length}` : ""}`);
    } catch (e) {
      fails.push(`${id}: exception ${String(e).split("\n")[0]}`);
      console.log(`XX ${id.padEnd(9)} exception: ${String(e).split("\n")[0]}`);
    } finally {
      await page.close().catch(() => {});
    }
  }

  await stop();
  server.close();
  if (fails.length) { console.error(`\nINTERACT(${ENGINE}) FAIL:\n  - ${fails.join("\n  - ")}`); process.exitCode = 1; }
  else console.log(`\nINTERACT(${ENGINE}): PASSED`);
}

main();
