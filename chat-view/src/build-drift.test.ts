// Build-drift banner in VS Code (the user 2026-07-13: "if anything gets out of sync I want to see a
// banner telling me to reload"). The VS Code panes run VSIX-BUNDLED webview code — no kernel-served
// page, no ?v= token, so the browser pages' shim check never runs here, and a pane's wsStale posts go
// to a parent that doesn't handle them. Instead the EXTENSION compares the `dv` (kernel dist token)
// riding every keepalive against its own bundled build stamp (__ROMP_BUILD__, baked by esbuild.js) and
// prompts ONCE when the installed bundle predates a rebuild. Source pins (the extension host needs the
// vscode module, so the wiring can't run under node --test).
import { test } from "node:test";
import assert from "node:assert";
import * as fs from "fs";
import * as path from "path";

const EXT = fs.readFileSync(path.resolve(process.cwd(), "src", "extension.ts"), "utf8");
const ESBUILD = fs.readFileSync(path.resolve(process.cwd(), "esbuild.js"), "utf8");

test("esbuild bakes a build stamp into the extension bundle", () => {
  // epoch SECONDS — the same clock as the kernel's dist token (newest dist/*.js mtime), so the two
  // compare directly with no unit conversion.
  assert.match(ESBUILD, /define:\s*\{\s*__ROMP_BUILD__:\s*String\(Math\.floor\(Date\.now\(\) \/ 1000\)\)\s*\}/);
});

test("the extension compares keepalive dv against the stamp and prompts once", () => {
  assert.ok(EXT.includes("declare const __ROMP_BUILD__: number;"), "the define is declared for tsc");
  assert.ok(EXT.includes("function maybeBuildNotice(dv: unknown)"), "the drift check exists");
  assert.ok(EXT.includes("if (buildNotified || !BUILD_STAMP || typeof dv !== \"number\" || dv <= BUILD_STAMP) return;"),
    "latched (one prompt per window), guarded when the stamp is absent, and only NEWER dv fires");
  assert.ok(EXT.includes("showInformationMessage"), "a prompt, never an auto-reload");
  assert.ok(!EXT.includes("reloadWindow"), "no auto window reload — the user acts on the prompt");
});

test("only panel pipes check drift — the passive status pipe never toasts", () => {
  assert.ok(EXT.includes('if (m && m.type === "ka" && !this.passive) maybeBuildNotice(m.dv);'),
    "the ka hook rides the pipe message handler, gated off the passive (status) pipe");
});
