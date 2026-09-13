// T394 (the user 2026-09-12, from a screenshot of the background fold): every row of the chat's background box sits in its KIND's
// section (Agents, Commands, Watches), one hue per kind for the dot and the caption word, and a tracked task nobody waits on (the
// judge audited its launch without a wait) lists in its kind's section, dimmed, with the verdict as a muted suffix, instead of
// under a section of its own. The header counts every row the list shows. Executed: the header's words; pinned: the row spec, the
// row builder, the sheet in both themes, the fixture. The served lab (tests/test_bg_kinds_browser.py) reads the computed colours.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { keptWord, listBreakdown, GROUP_TITLE, ROW_KINDS, type AwaitRow } from "./spin-caption";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
const FIXTURE = fs.readFileSync(path.resolve(process.cwd(), "..", "tools", "ui-verify", "fixtures", "awaiting-rows-chat.html"), "utf8");
const fn = (name: string) => RENDER.slice(RENDER.indexOf("function " + name + "("), RENDER.indexOf("\n}\n", RENDER.indexOf("function " + name + "(")));
const UI_RULES = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "CLAUDE.md"), "utf8");

test("the header's words: the breakdown of every row it is given, then how many of them wear the verdict; either alone when the other is empty", () => {
  const rows: AwaitRow[] = [{ kind: "agents", id: "a1", label: "Map the parser" }, { kind: "commands", id: "c1", label: "Build the docs" }, { kind: "watches", id: "w1", label: "the CI run" }];
  assert.equal(keptWord(0), "", "none kept: no word");
  assert.equal(keptWord(1), "1 kept running");
  assert.equal(keptWord(2), "2 kept running");
  assert.equal(listBreakdown(rows, 1), "1 agent · 1 command · 1 watch · 1 kept running");
  assert.equal(listBreakdown(rows, 0), "1 agent · 1 command · 1 watch", "no kept rows: the breakdown as before");
  assert.equal(listBreakdown([], 1), "1 kept running", "only a kept row: no leading separator");
  assert.equal(listBreakdown([], 0), "");
});

test("the sections are the kinds, in the rows' display order, and no section of its own remains for the kept rows", () => {
  const body = fn("renderBgTasks");
  assert.deepEqual([...ROW_KINDS], ["agents", "commands", "watches", "peer", "timer"]);
  for (const k of ["agents", "commands", "watches"]) assert.ok(GROUP_TITLE[k], "a title for " + k);
  assert.match(body, /const kept = leftovers\.map\(\(t\) => taskRowSpec\(t, awaited\.has\(t\.id\), services\.has\(t\.id\)\)\);/, "the tracked tasks the kernel's rows do not name become rows of their kind; the judge's verdict rides in");
  assert.match(body, /const services = new Set<string>\(s\.status\.bgServiceIds \|\| \[\]\);/, "the kernel ships the judge's furniture verdict as launch ids (round one, medium 2)");
  assert.match(body, /const keptN = kept\.filter\(\(row\) => row\.kept\)\.length;/, "the header counts the rows wearing the verdict, none other (round one, medium 1)");
  assert.match(body, /const sections: \{ kind: string; rows: AwaitRow\[\] \}\[\] = \[\.\.\.ROW_KINDS, "other"\]\s*\n\s*\.filter\(\(k\) => groups\.some\(\(g\) => g\.kind === k\) \|\| kept\.some\(\(row\) => row\.kind === k\)\)/,
    "a kind the rows bring, or one only a kept row brings, in display order");
  assert.match(body, /for \(const g of sections\) \{\s*\n\s*if \(headers\) \{ const gh = el\("div", "bg-group-head"\); gh\.textContent = GROUP_TITLE\[g\.kind\] \|\| "Other"; list\.appendChild\(gh\); \}/);
  assert.match(body, /for \(const row of kept\) if \(row\.kind === g\.kind\) list\.appendChild\(bgRow\(row, sid\)\);/, "the kept rows of the kind follow its awaited rows");
  assert.doesNotMatch(RENDER, /BG_LEFTOVER_TITLE|"Also running"/, "the section and its title are gone");
  assert.match(body, /const counted: AwaitRow\[\] = \[\.\.\.items, \.\.\.kept\.map\(\(row\) => \(\{ kind: row\.kind \|\| "commands", id: row\.id, label: row\.label \}\)\)\];/,
    "every listed row is counted, the tracked tasks by kind (round two, medium: a box whose only row was a tracked task read a separator with nothing after it)");
  assert.match(body, /lab\.textContent = "In the background · " \+ listBreakdown\(counted, keptN\);/, "the working header counts every row it lists");
  assert.match(body, /lab\.textContent = "Awaiting " \+ word \+ " · " \+ listBreakdown\(counted, keptN\);/, "…and the mixed idle header");
  assert.match(body, /if \(kept\.length\) lab\.append\(" · " \+ listBreakdown\(counted, keptN\)\);/, "…and the peer-named idle header counts every listed row, the peer rows as peers (round four)");
  assert.match(body, /counts every TOP-LEVEL row the list shows, by kind, awaited or not, a\n\s*\/\/ peer row as a peer/, "the rule's sentence names what it counts");
  assert.match(body, /An agent's OWN waits, drawn as sub-rows under it, are the agent's and stay out of the count/, "…and what it excludes, and why");
  assert.match(body, /lab\.textContent = "Awaiting" \+ \(word \? " " \+ word : ""\) \+ " · " \+ why\.replace\(\/\^\(waiting on\|awaiting\)\\s\+\/i, ""\) \+ \(kept\.length \? " · " \+ listBreakdown\(counted, keptN\) : ""\);/,
    "…and the one-kind idle header counts the rows beyond the wait's, by kind, with the kept subset (round three, low 3)");
  assert.match(body, /THE HEADER'S RULE \(T394 round three, lows 1 and 2; round four\): the leading word is the wait and its count is the awaited rows/, "the rule, stated where the header is built");
  assert.match(body, /subset of those rows wearing the judge's verdict, never a further partition/, "…the kept count is a subset, never a partition");
  assert.doesNotMatch(body, /listBreakdown\(items, keptN\)/, "no header reads the kernel's rows alone");
  const key = fn("awaitKey");
  assert.match(key, /st\.awaitingTaskIds \|\| \[\], st\.bgServiceIds \|\| \[\], st\.awaitingItems \|\| \[\]/, "a verdict-only frame repaints the box (round two, low 1)");
  assert.match(body, /const worst = tasks\.reduce\(\(w, t\) => \(BG_RANK\[t\.status\] \|\| 0\) > \(BG_RANK\[w\] \|\| 0\) \? t\.status : w, tasks\.length \? \(tasks\[0\]\.status \|\| "running"\) : "running"\);/,
    "the header dot seeds from the tasks' own statuses: a completed-only box reads completed (round two, low 2)");
});

test("every row spec carries its kind, and a tracked task is kept only where the kernel's verdict names it a service, while it runs", () => {
  const task = fn("taskRowSpec"), aw = fn("awaitRowSpec"), spec = RENDER.slice(RENDER.indexOf("interface BgRowSpec {"), RENDER.indexOf("\n}\n", RENDER.indexOf("interface BgRowSpec {")));
  assert.match(spec, /kind\?: string \| null;/);
  assert.match(spec, /kept\?: boolean;/);
  assert.match(task, /kind: t\.agentId \? "agents" : "commands", kept: service && status === "running",/, "an agent-shaped task is an agent; the rest are commands; kept only on the judge's verdict, and only while running (round one, medium 2 and low 1)");
  assert.match(RENDER, /function taskRowSpec\(t: BgTask, awaited: boolean, service: boolean\): BgRowSpec \{/);
  assert.doesNotMatch(task, /kept: !awaited/, "never inferred from a missing row");
  assert.match(aw, /return \{ id, status: "running", caption: "running", kind: "agents",/);
  assert.match(aw, /return \{ id, status, caption: status, kind: "commands",/);
  assert.match(aw, /return \{ id, status: "armed", caption: "armed", kind: "watches",/);
  assert.match(aw, /return \{ id, status: "waiting", kind: "peer",/);
  assert.match(aw, /kind: it\.kind, label: it\.label \|\| it\.kind, since: it\.since \};/, "a timer or a newer kernel's kind keeps its own name");
});

test("the row wears its kind and its verdict: bg-kind-<kind>, bg-kept, and the muted suffix beside the label", () => {
  const row = fn("bgRow");
  assert.match(RENDER, /const BG_KEPT_WORD = "· kept running, not waited on";/);
  assert.match(row, /\(t\.kind \? " bg-kind-" \+ t\.kind : ""\) \+ \(t\.kept \? " bg-kept" : ""\)/);
  assert.match(row, /rh\.appendChild\(sum\);\s*\n\s*if \(t\.kept\) \{ const kw = el\("span", "bg-kept-word"\); kw\.textContent = BG_KEPT_WORD; rh\.appendChild\(kw\); \}/, "the suffix follows the label, before the cluster");
});

test("the sheet: one hue per kind, status overriding for failed and completed, the kept row dimmed without element opacity, the cream caption deepened", () => {
  const root = CSS.slice(CSS.indexOf(":root {"), CSS.indexOf("\n}", CSS.indexOf(":root {")));
  const light = CSS.slice(CSS.indexOf("body.theme-light {"), CSS.indexOf("\n}", CSS.indexOf("body.theme-light {")));
  assert.match(root, /--kind-command: var\(--accent\);/, "dark: the accent blue the timeline lane icons wear");
  assert.match(light, /--kind-command: #356890;/, "cream: the accent's hue at OKLCH lightness 0.50 (the light accent is an orange)");
  const rules = CSS.slice(CSS.indexOf(".bg-task { --bgt: var(--st-working-bg); }"), CSS.indexOf(".bg-group-head {"));
  const order = [".bg-task.bg-kind-agents { --bgt: var(--st-working-bg); }", ".bg-task.bg-kind-commands { --bgt: var(--kind-command); }",
                 ".bg-task.bg-kind-watches { --bgt: var(--st-awaitbg-bg); }", ".bg-task.bg-failed { --bgt: var(--st-blocked-bg); }", ".bg-task.bg-completed { --bgt: var(--dim); }"];
  let at = -1;
  for (const r of order) { const i = rules.indexOf(r); assert.ok(i > at, "in cascade order, the status rules after the kind rules: " + r); at = i; }
  assert.doesNotMatch(rules, /\.bg-task\.bg-completed \{ --bgt: var\(--st-ready-bg\); \}/, "the ready blue would collide with the command hue");
  // the kept rules sit AFTER the row label's own rule: the layout pin reads the first `.bg-sum {` as the label's (bg-tasks-layout.test.ts)
  assert.ok(CSS.indexOf(".bg-task.bg-kept .bg-sum {") > CSS.indexOf("\n.bg-sum {"), "the kept label rule follows the label rule");
  assert.match(CSS, /\.bg-task\.bg-kept \.bg-dot \{ background: color-mix\(in srgb, var\(--bgt\) 45%, var\(--dim\)\); \}/, "the kept dot is a colour, the hue greyed toward the dim ink (round one, low 2), never element opacity");
  assert.doesNotMatch(CSS, /\.bg-kept \.bg-dot \{[^}]*opacity/);
  assert.match(CSS, /\.bg-fold-head\.bg-completed \{ --bgt: var\(--dim\); \}/, "the header's completed tint follows the rows (round one, low 4)");
  assert.match(CSS, /\.bg-task\.bg-kept \.bg-sum \{ color: var\(--dim\); \}/);
  assert.match(CSS, /\.bg-kept-word \{ flex: 0 0 auto; font-size: 0\.82em; color: var\(--dim\); white-space: nowrap; \}/);
  assert.doesNotMatch(CSS, /\.bg-task\.bg-kept \{[^}]*opacity/, "the row itself never dims by opacity: every caption would fall under 4.5:1");
  assert.match(CSS, /body\.theme-light \.bg-status \{ color: oklch\(from var\(--bgt\) 0\.46 c h\); \}/, "the T390 lightness rule for the caption word on cream");
  assert.match(CSS, /\.bg-status \{[^}]*color: var\(--bgt\); \}/, "…over the plain hue, which an engine without relative colours keeps");
});

test("the accent-is-never-a-status-colour rule names its one exception, in the sheet and the UI rules (round one, low 5)", () => {
  assert.match(CSS, /ONE exception \(the user 2026-09-12, T394\): the background box's command rows wear it as their KIND hue/);
  assert.match(UI_RULES, /ONE exception, the user's choice of 2026-09-12 \(T394\): the background box's COMMAND rows wear\nthe accent blue as their KIND hue/);
});

test("the fixture mirrors the builder: every row wears its kind class", () => {
  const rows = FIXTURE.match(/<div class="bg-task [^"]*">/g) || [];
  assert.ok(rows.length >= 6, "rows in the fixture: " + rows.length);
  for (const r of rows) assert.match(r, /bg-kind-(agents|commands|watches)/, r);
});
