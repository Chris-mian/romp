// The model picker's current ✓ (the chat's isCurrentMeta in render.ts and the timeline lane menu's twin in
// ui/romp-timeline-view.js): the session's model badge is a display name ("Fable 5.1", the leading word of which
// is the family row's value) or, for a model the operator's API gateway declares (ROMP_ROUTER_MODELS), the id
// VERBATIM. The rule downcases both sides and matches the whole badge or its leading WORD (a space boundary):
// before this (review round two, 2026-09-22) the badge alone was downcased and prefix-matched against the row's
// verbatim value, so a mixed-case id (Qwen/Qwen3-235B) never ticked its own row and a declared prefix pair
// (gpt-6 and gpt-6-astra) double-ticked. Both twins are executed as written; every existing control case stays.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const TL = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");
const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

function fnSource(src: string, name: string): string {
  const i = src.indexOf(`function ${name}(`);
  assert.ok(i >= 0, `${name} is defined`);
  const j = src.indexOf("\n}\n", i);
  return src.slice(i, j + 3);
}
type Tick = (kind: string, st: any, value: string) => boolean;
const tlTick = new Function(fnSource(TL, "isCurrentMeta") + "\nreturn isCurrentMeta;")() as Tick;
const chatTick = new Function(fnSource(RENDER, "isCurrentMeta")
  .replace("(kind: MetaKind, st: Status, value: string): boolean {", "(kind, st, value) {") + "\nreturn isCurrentMeta;")() as Tick;
const both: Array<[string, Tick]> = [["chat", chatTick], ["timeline", tlTick]];

test("a declared gateway id ticks its own row whatever its case, on both surfaces", () => {
  for (const [name, tick] of both) {
    assert.equal(tick("model", { model: "Qwen/Qwen3-235B" }, "Qwen/Qwen3-235B"), true, name + ": the badge is the id verbatim, the row's value too");
    assert.equal(tick("model", { model: "qwen/qwen3-235b" }, "Qwen/Qwen3-235B"), true, name + ": a badge the gateway downcased still ticks");
    assert.equal(tick("model", { model: "gw-7-nova" }, "gw-7-nova"), true, name + ": a plain declared id");
  }
});

test("a declared prefix pair ticks one row, never both, on both surfaces", () => {
  for (const [name, tick] of both) {
    assert.equal(tick("model", { model: "gpt-6-astra" }, "gpt-6"), false, name + ": gpt-6-astra is not gpt-6");
    assert.equal(tick("model", { model: "gpt-6-astra" }, "gpt-6-astra"), true, name + ": …it is gpt-6-astra");
    assert.equal(tick("model", { model: "gpt-6" }, "gpt-6-astra"), false, name + ": and gpt-6 is not gpt-6-astra");
    assert.equal(tick("model", { model: "gpt-6" }, "gpt-6"), true);
  }
});

test("the control cases: a first-party display name ticks its family on the leading word, and nothing else", () => {
  for (const [name, tick] of both) {
    assert.equal(tick("model", { model: "Fable 5.1" }, "fable"), true, name + ": the leading word");
    assert.equal(tick("model", { model: "Opus 4.8" }, "opus"), true, name);
    assert.equal(tick("model", { model: "Opus" }, "opus"), true, name + ": the capitalised alias before the live name lands");
    assert.equal(tick("model", { model: "Fable 5.1" }, "opus"), false, name);
    assert.equal(tick("model", { model: "Fable 5.1" }, "fab"), false, name + ": a word's prefix is not the word");
    assert.equal(tick("model", { model: "" }, "fable"), false, name + ": no badge, no tick");
    assert.equal(tick("model", {}, "fable"), false, name + ": no model field at all");
    assert.equal(tick("effort", { effort: "High" }, "high"), true, name + ": effort matches exactly, case-folded");
    assert.equal(tick("effort", { effort: "high" }, "hi"), false, name + ": …never on a prefix");
  }
});

test("the two twins agree on every case", () => {
  const cases: Array<[string, any, string]> = [
    ["model", { model: "Qwen/Qwen3-235B" }, "Qwen/Qwen3-235B"], ["model", { model: "gpt-6-astra" }, "gpt-6"],
    ["model", { model: "Fable 5.1" }, "fable"], ["model", { model: "Fable 5.1" }, "fab"], ["model", { model: "gpt-5-test" }, "gpt-5-test"],
    ["effort", { effort: "medium" }, "medium"], ["effort", { effort: "medium" }, "med"],
  ];
  for (const [k, st, v] of cases) assert.equal(chatTick(k, st, v), tlTick(k, st, v), JSON.stringify([k, st, v]));
});
