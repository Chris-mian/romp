// Extra models from your API gateway (2026-09-21), pinned at the source like the other webview tests (the gear has
// no jsdom harness). An install whose sessions reach the API through a gateway of its own can offer the model
// families that gateway serves in every model picker, beside the Claude families; the operator declares them with
// ROMP_ROUTER_MODELS in service.env (read when the service starts), and the switch decides whether the pickers offer
// them. The switch is a per-install kernel-side checkbox in the gear's General tab, under This machine beside
// Conserve memory (the gateway is THIS machine's, like its memory policy), gesture-stamped like every kernel-side
// setting the gear posts, filled from /version, named in the stale-gesture toast, and deliberately NOT in
// federation's KERNEL_SETTING set nor the kernel's mesh-adopted table: it never propagates. No echo frame of its own:
// an applied flip changes the catalog, the kernel sends its models frame, and the gear's re-read repaints the pickers
// and the row's status line (rs-router-line) from the authed /models payload's `router` section.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const ROOT = path.resolve(process.cwd(), "..");
const read = (...p: string[]) => fs.readFileSync(path.join(ROOT, ...p), "utf8");
const GEAR = read("ui", "webview", "gear.js");
const FED = read("ui", "webview", "federation.ts");
const KERNEL = read("kernel", "kernel.py");

test("the gear has an Extra models from your API gateway checkbox under General, This machine, after Conserve memory and before Updates, gesture-stamped, filled from /version, with a live status line", () => {
  assert.ok(GEAR.includes("id=rs-router>"), "the checkbox exists in the gear markup");
  const at = GEAR.indexOf("id=rs-router>");
  assert.ok(GEAR.indexOf("id=rs-conserve") > 0 && GEAR.indexOf("id=rs-updates") > 0, "both neighbours exist (indexOf's -1 would pass the order check)");
  assert.ok(GEAR.indexOf("id=rs-conserve") < at && at < GEAR.indexOf("id=rs-updates"), "…after Conserve memory and before Updates install automatically");
  const sec = GEAR.indexOf(">This machine</div>");
  assert.ok(sec > 0 && sec < at, "…under the This machine section header");
  assert.ok(!GEAR.slice(sec, at).includes("rs-sec"), "…with no other section header between (no header of its own: the General heads are pinned)");
  assert.ok(GEAR.indexOf("data-pane=general") > 0 && GEAR.indexOf("data-pane=chat") > 0, "both panes exist");
  assert.ok(GEAR.indexOf("data-pane=general") < at && at < GEAR.indexOf("data-pane=chat"), "…in the General tab");
  const row = GEAR.slice(GEAR.lastIndexOf("<label", at), GEAR.indexOf("</label>", at) + 8);
  assert.match(row, /<b>Extra models from your API gateway<\/b>/, "the user's words, not the wire's");
  assert.ok(row.includes("<span class=rs-mixed hidden></span>"), "the house shape: the mixed mark slot beside the label");
  assert.ok(row.includes("<span class=rs-sub>Also offer the models your API gateway serves in every model picker. Declare them with ROMP_ROUTER_MODELS in service.env; read when the service starts. Off: Claude models only.</span>"),
    "the sub-copy in the user's words, exactly");
  assert.ok(row.includes("<span class=rs-line id=rs-router-line></span>"), "the always-visible status line rides inside the row");
  assert.equal((row.match(/<span/g) || []).length, (row.match(/<\/span>/g) || []).length, "every span the row opens it closes");
  assert.ok(GEAR.includes("rtr = document.getElementById('rs-router'), rtrLine = document.getElementById('rs-router-line')"), "the box and its line are looked up beside Conserve memory's");
  assert.ok(GEAR.includes("post({ type: 'setRouterModels', enabled: rtr.checked, gt: gclock.stamp('router-models') })"),
    "the click posts the kernel's designed message with the gesture stamp minted in the literal");
  assert.ok(!GEAR.includes("scoped({ type: 'setRouterModels'"), "…unscoped: a per-install setting has no machine selector");
  assert.ok(GEAR.includes("rtr.checked = !!v.routerModels"),
    "the box always shows the kernel's persisted answer, never a page default");
  assert.match(GEAR, /STALE_LABELS = \{[\s\S]*?'router-models': 'Extra models from your API gateway'/,
    "a stood-down gesture toasts under the row's own name");
  assert.match(GEAR, /STALE_TYPE = \{[\s\S]*?'router-models': 'setRouterModels'/,
    "the toast's Apply anyway may re-issue this one setting");
  // the status line: written from the authed /models payload's `router` section, wherever the gear takes one; what
  // it SAYS is executed below (the fillRouterLine tests), not pinned at the source
  const fnAt = GEAR.indexOf("function fillRouterLine(d) {");
  assert.ok(fnAt > 0, "the status line has one writer");
  // wired through the cache block's paint hook: the block is lifted and run alone by gear-models-frame.test.ts, so the
  // writer lives outside it and the block reaches it through a variable it leaves null
  const blockStart = GEAR.indexOf("  var choices = null");
  const blockStop = GEAR.indexOf("\n  });\n", GEAR.indexOf("m.type !== 'models'", blockStart));
  assert.ok(blockStart > 0 && blockStop > blockStart, "the cache block located");
  const block = GEAR.slice(blockStart, blockStop);
  assert.ok(block.includes("var onChoices = null;"), "the block declares the hook, null");
  const paintAt = block.indexOf("function paintChoices() {");
  assert.ok(paintAt > 0 && block.slice(paintAt, block.indexOf("\n  }\n", paintAt)).includes("if (onChoices) onChoices(choices);"),
    "…fired at the end of every paint, with the list that won (a stale payload paints nothing, so the line never moves for no reason)");
  assert.ok(!block.includes("fillRouterLine") && !block.includes("rtrLine"), "…and the block names neither the writer nor the element (the lifted harness has neither)");
  assert.ok(fnAt > blockStop, "the writer sits after the block");
  assert.ok(GEAR.includes("\n  onChoices = fillRouterLine;\n"), "…and is the hook's one assignee");
  const frame = GEAR.slice(GEAR.indexOf("if (!m || (m.type !== 'models' && m.type !== 'wsup')) return;"), blockStop);
  assert.ok(frame.includes("if (d && Array.isArray(d.models) && adoptChoices(d)) paintChoices();"),
    "the models frame (the kernel's only signal for an applied flip: no echo frame) and the shim's wsup frame (a kernel restart: the documented way to change the declared list) repaint, which refreshes the line");
});

// fillRouterLine, executed: the function is lifted out of gear.js (the way gear-models-frame.test.ts lifts the cache
// block) and run against a stand-in element, so these pin what the line SAYS for each state of the payload's
// `router` section — {enabled, declared: [ids], gateway: true|false|null, error: string|null}. The kernel probes the
// gateway only while the switch is on (gateway null = not probed) and files an advisory only while on.
function liftRouterLine(): { line: { textContent: string }; fill: (d: any) => void } {
  const start = GEAR.indexOf("  function fillRouterLine(d) {");
  const stop = GEAR.indexOf("\n  }\n", start) + "\n  }\n".length;
  assert.ok(start > 0 && stop > start, "fillRouterLine located");
  const line = { textContent: "unset" };
  const fill = new Function("rtrLine", GEAR.slice(start, stop) + "\n  return fillRouterLine;")(line) as (d: any) => void;
  return { line, fill };
}
const router = (over: any) => ({ router: { enabled: true, declared: ["gw-6-astra", "gw-7-nova"], gateway: true, error: null, ...over } });

test("executed: the status line is blank for a payload with no router section (an older kernel), and for a missing element", () => {
  const { line, fill } = liftRouterLine();
  fill({ models: [], efforts: [] });
  assert.equal(line.textContent, "");
  line.textContent = "unset";
  fill(null);
  assert.equal(line.textContent, "");
  line.textContent = "unset";
  fill({ router: "yes" });
  assert.equal(line.textContent, "", "a router field that is not an object counts as none");
  const start = GEAR.indexOf("  function fillRouterLine(d) {");
  const noEl = new Function("rtrLine", GEAR.slice(start, GEAR.indexOf("\n  }\n", start) + 4) + "\n  return fillRouterLine;")(null) as (d: any) => void;
  assert.doesNotThrow(() => noEl(router({})), "no rs-router-line in the document: nothing to write, nothing thrown");
});

test("executed: an advisory wins over the count, verbatim (a swap of the two branches fails here)", () => {
  const { line, fill } = liftRouterLine();
  fill(router({ error: "the gateway address could not be read" }));
  assert.equal(line.textContent, "the gateway address could not be read", "…with two declared and a gateway, the advisory still shows");
  fill(router({ declared: [], error: "ROMP_ROUTER_MODELS named no model" }));
  assert.equal(line.textContent, "ROMP_ROUTER_MODELS named no model", "…and over the empty-declaration wording");
});

test("executed: nothing declared shows nothing on its own, on or off; the kernel's advisory names the variable when that is the case", () => {
  // on with nothing declared and no advisory is the URL-only install: the listing's rows are offered and the line has
  // nothing to add (the verify round's find: it read "Nothing declared yet" beside three gateway rows)
  const { line, fill } = liftRouterLine();
  fill(router({ declared: [] }));
  assert.equal(line.textContent, "");
  fill(router({ enabled: false, declared: [], gateway: null }));
  assert.equal(line.textContent, "", "off with nothing declared: a blank line under an off switch");
  line.textContent = "unset";
  fill(router({ enabled: false, gateway: null, declared: undefined }));
  assert.equal(line.textContent, "", "…a declared field that is not a list reads as nothing declared");
});

test("executed: N declared, and the gateway named missing only when the probe RAN and said so", () => {
  const { line, fill } = liftRouterLine();
  fill(router({ gateway: true }));
  assert.equal(line.textContent, "2 declared");
  fill(router({ gateway: false }));
  assert.equal(line.textContent, "2 declared · no gateway configured");
  fill(router({ enabled: false, gateway: null }));
  assert.equal(line.textContent, "2 declared", "off: the gateway is not probed (null), so nothing is said about it");
  fill(router({ declared: ["gw-6-astra"], gateway: null }));
  assert.equal(line.textContent, "1 declared", "null is not-probed whatever the switch says");
});

test("Extra models from your API gateway is per-install: not a KERNEL_SETTING, not mesh-adopted, not a converging row", () => {
  const setSrc = FED.match(/const KERNEL_SETTING = new Set\(\[([\s\S]*?)\]\)/);
  assert.ok(setSrc, "federation.ts's KERNEL_SETTING set located");
  assert.ok(!setSrc![1].includes("setRouterModels"), "the set must not carry it: the gateway is this machine's");
  assert.ok(!FED.includes("setRouterModels"), "…and no other federation path names it either");
  const mesh = KERNEL.match(/_MESH_ADOPTED_SETTINGS = \(([\s\S]*?)\)\n_SETTINGS_STORES/);
  assert.ok(mesh, "kernel.py's mesh-adopted settings table located");
  assert.ok(!mesh![1].includes('"router-models"') && !mesh![1].includes("routerModels"), "…nor the mesh-adopted settings table on the kernel side");
  for (const table of ["PROPOSAL_ROWS", "STORE_KEY"]) {
    const t = GEAR.match(new RegExp("var " + table + " = \\{([^}]*)\\}"));
    assert.ok(t, "gear.js's " + table + " located");
    assert.ok(!t![1].includes("router-models"), table + " is the converging four's: this row raises no proposal and wears no mark");
  }
});

test("the kernel keeps the switch: a reader, /version carries it, a WS arm, and a gt store", () => {
  assert.ok(KERNEL.includes("def _router_models_on("), "the switch's reader exists");
  const vAt = KERNEL.indexOf("def _version_info(");
  assert.ok(vAt > 0, "_version_info located");
  const vBody = KERNEL.slice(vAt, KERNEL.indexOf("\ndef ", vAt + 1));
  assert.ok(vBody.includes('"routerModels":'), "/version carries it for the gear's fill");
  assert.ok(KERNEL.includes('"setRouterModels"'), "the WS op exists");
  const gt = KERNEL.match(/_GT_STORES = \(([\s\S]*?)\)/);
  assert.ok(gt, "_GT_STORES located");
  assert.ok(gt![1].includes('"router-models"'), "the store is gt-ordered like every stamped setting");
});

test("a kernel restart re-reads the model list on both surfaces: the chat's picker and the gear's cache block take the shim's wsup frame", () => {
  const RENDER = read("ui", "webview", "render.ts");
  assert.match(RENDER, /\n  if \(m\.type === "wsup"\) loadModelChoices\(\);\n/, "the chat re-reads through the ONE reader the models frame uses (no second fetch path)");
  assert.match(RENDER, /else if \(m\.type === "models"\) loadModelChoices\(\);/, "…which is still the models frame's");
  assert.ok(GEAR.includes("if (!m || (m.type !== 'models' && m.type !== 'wsup')) return;"), "the gear's cache block re-reads on the same frame");
});

test("source: an empty status line takes no layout (the browser leg measures it; this pin is the weaker, CI-visible form)", () => {
  const css = read("ui", "webview", "gear.css");
  assert.match(css, /#rsettings \.rs-line:empty \{ display: none; \}/);
});
