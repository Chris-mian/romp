// The Extra models from your API gateway row's status line (rs-router-line) when it has NOTHING to say — a stock
// install: switch off, nothing declared, an older kernel's /models with no `router` section — must take no layout, so
// the row stands exactly as tall as Conserve memory's beside it. Before the :empty rule an empty .rs-line kept its
// display:block and 1px top margin, and the row rendered a pixel taller than its neighbour (review find, 2026-09-22).
// Driven in headless Chromium over the REAL gear module (gear.js) and its stylesheet, the gear-judge-fast-browser
// pattern: a source pin cannot measure a box. The gear is opened against a fake kernel (/models, /version answered
// with synthetic payloads) and the two rows are measured; then a /models payload with two declared gateway families
// is fed through a models frame and the line is shown, taller row and all, so the test proves the rule hides only
// an EMPTY line. Skips with a stated reason without a playwright browser (CI installs none). Synthetic values only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { createRequire } from "node:module";

const EXT = process.cwd();                                        // npm test runs in vscode-extension
const requireCjs = createRequire(path.join(EXT, "package.json"));
const UI = path.resolve(EXT, "..", "ui", "webview");
const GEAR_CSS = fs.readFileSync(path.join(UI, "gear.css"), "utf8");

const ENTRY = `
const { initGear } = require("./gear.js");
(window as any).__posts = [];
initGear((m: any) => { (window as any).__posts.push(m); });
`;

function bundle(): string {
  const esbuild = requireCjs("esbuild");
  const r = esbuild.buildSync({
    stdin: { contents: ENTRY, resolveDir: UI, loader: "ts", sourcefile: "gear-router-line-entry.ts" },
    bundle: true, write: false, format: "iife", platform: "browser", target: "es2020",
    nodePaths: [path.join(EXT, "node_modules")], logLevel: "silent",
  });
  return r.outputFiles[0].text;
}

const PAGE_HTML = `<!DOCTYPE html><html><head><meta charset=utf-8><style>${GEAR_CSS}</style></head><body>
<script src=/dist/gear.js></script></body></html>`;
const FAMILIES = [{ value: "opus", label: "Opus", versions: [] }, { value: "sonnet", label: "Sonnet", versions: [] }];
const EFFORTS = [{ value: "", label: "Default" }, { value: "low", label: "Low" }];
// the stock install's answer: the switch off, nothing declared, no gateway probed (the kernel probes only while ON)
const MODELS_STOCK = { rev: 10, models: FAMILIES, efforts: EFFORTS, router: { enabled: false, declared: [], gateway: null, error: null } };
// …and a later, newer catalog with two declared gateway families (ids invented for the test) and the switch on
const MODELS_DECLARED = { rev: 11, models: FAMILIES.concat([{ value: "gw-6-astra", label: "Astra", versions: [] }, { value: "gw-7-nova", label: "Nova", versions: [] }]),
  efforts: EFFORTS, router: { enabled: true, declared: ["gw-6-astra", "gw-7-nova"], gateway: true, error: null } };
const VERSION = { judgeModel: "opus", judgeEffort: "", indexModel: "haiku", indexEffort: "low", distillModel: "triage", distillEffort: "triage",
  judgeConcurrency: "", commentModel: "session", commentEffort: "session", commentFast: "session",
  judgeFast: "on", distillFast: "on", indexFast: "on", conserveMemory: false, routerModels: false,
  autoNudge: true, settingsGt: {}, updateMode: "off" };

let pw: any = null;
try { pw = requireCjs("playwright"); } catch { pw = null; }

type Rows = { conserve: number; router: number; lineDisplay: string; lineText: string };

// the two rows' rendered heights (the label element IS the .rs-row), the status line's computed display and its text
const measure = (page: any): Promise<Rows> => page.evaluate(() => {
  const row = (id: string) => (document.getElementById(id) as HTMLElement).closest(".rs-row") as HTMLElement;
  const line = document.getElementById("rs-router-line") as HTMLElement;
  return { conserve: row("rs-conserve").getBoundingClientRect().height, router: row("rs-router").getBoundingClientRect().height,
    lineDisplay: getComputedStyle(line).display, lineText: line.textContent || "" };
});

test("the Extra models row stands as tall as Conserve memory's while its status line is empty, and grows only when the line says something", async (t) => {
  if (!pw) { t.skip("playwright is not installed under vscode-extension; the browser leg needs it (CI installs no browsers)"); return; }
  let browser: any;
  try { browser = await pw.chromium.launch(); }
  catch (e) { t.skip("no playwright browser on this machine; the browser leg needs one (CI installs none): " + String((e as Error).message).split("\n")[0]); return; }
  const errors: string[] = [];
  let models: unknown = MODELS_STOCK;
  try {
    const js = bundle();
    const page = await browser.newPage({ viewport: { width: 1000, height: 900 } });
    page.on("pageerror", (e: Error) => { errors.push(e.message); });
    await page.route("**/*", (route: any) => {
      const u = new URL(route.request().url());
      const json = (o: unknown) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(o) });
      if (u.hostname !== "romp.test") return route.fulfill({ status: 404, body: "" });
      if (u.pathname === "/gear") return route.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: PAGE_HTML });
      if (u.pathname === "/dist/gear.js") return route.fulfill({ status: 200, contentType: "application/javascript", body: js });
      if (u.pathname === "/models") return json(models);
      if (u.pathname === "/version") return json(VERSION);
      if (u.pathname === "/tunnels") return json({ tunnels: [] });
      return json({});   // /palette, /analytics and the rest: empty answers, nothing under test
    });
    await page.goto("http://romp.test/gear");
    await page.waitForFunction(() => Array.isArray((window as any).__posts) && !!document.getElementById("rs-router"), null, { timeout: 10000 });
    await page.evaluate(() => { window.postMessage({ romp: "openSettings", tab: "general" }, "*"); });   // both rows live under General, This machine
    // the fill has run once a box holds the kernel's flag (only fill() writes it); the page-load /models has been
    // painted once a family select holds a row (paintChoices fills them from the payload the open's fetch adopted)
    await page.waitForFunction(() => (document.getElementById("rs-indexfast") as HTMLInputElement).checked === true
      && (document.getElementById("rs-judgemodel") as HTMLSelectElement).options.length > 0, null, { timeout: 10000 });

    const stock = await measure(page);
    assert.equal(stock.lineText, "", "a stock install: the line has nothing to say");
    assert.ok(stock.conserve > 0, "the Conserve memory row is rendered (a hidden pane would measure 0 and pass an equality by accident)");
    assert.equal(stock.router, stock.conserve, "the Extra models row is exactly as tall as Conserve memory's beside it (an empty line kept its 1px margin before)");
    assert.equal(stock.lineDisplay, "none", "…because an empty line takes no layout (gear.css .rs-line:empty)");

    // the catalog grows (a flip applied, or a restart with a declared list): the kernel's models frame re-reads /models
    models = MODELS_DECLARED;
    await page.evaluate(() => { window.postMessage({ type: "models", rev: 11 }, "*"); });
    await page.waitForFunction(() => (document.getElementById("rs-router-line") as HTMLElement).textContent === "2 declared", null, { timeout: 10000 });
    const declared = await measure(page);
    assert.equal(declared.lineDisplay, "block", "a line with something to say is shown");
    assert.ok(declared.router > declared.conserve, "…and the row grows by the line: the rule hides only an EMPTY line");
    assert.deepEqual(errors, [], "no page errors");
  } finally {
    await browser.close();
  }
});
