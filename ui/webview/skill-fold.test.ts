// Skill-invocation fold (the user 2026-07-08): the Skill tool row names the skill and holds its full
// instructions as the tool's collapsed-by-default fold body (kernel-joined ev.skillMd) — never a
// separate always-expanded note box while the turn runs. Source pins (render.ts has import-time DOM
// side effects, so no test imports it as a module).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "bin", "romp-kernel"), "utf8");
const EM = fs.readFileSync(path.resolve(process.cwd(), "..", "bin", "romp-event-model"), "utf8");
const SDK = fs.readFileSync(path.resolve(process.cwd(), "..", "bin", "romp_sdk_backend.py"), "utf8");

test("the Skill tool renders its instructions as a collapsed inlineFold, with the skill named on the head", () => {
  assert.match(RENDER, /skillMd\?: string;/, "the tool ChatEvent carries the kernel-joined markdown");
  assert.match(RENDER, /\} else if \(ev\.name === "Skill"\) \{/, "Skill has its own render branch");
  assert.match(RENDER, /inlineFold\(head, turn, `skill · \$\{countLines\(ev\.skillMd\)\} lines`, box, fkey\);/,
               "the content is the fold body — inlineFold is collapsed by default");
  assert.match(RENDER, /o\.skill === "string"/, "the head shows WHICH skill from the tool input");
});

test("the kernel joins the flagged skill atom onto the invoking Skill tool event (both paths emit it)", () => {
  assert.match(KERNEL, /if a\.get\("skillMd"\):/, "build_session consumes the flagged atom");
  assert.match(KERNEL, /_ev\.get\("kind"\) == "tool" and _ev\.get\("name"\) == "Skill" and not _ev\.get\("skillMd"\)/,
               "joined to the newest unfilled Skill event — invocation order");
  assert.match(EM, /SKILL_CONTENT_RE = re\.compile\(r"\^\\s\*Base directory for this skill:"\)/);
  assert.match(SDK, /_SKILL_CONTENT_RE = re\.compile\(r"\^\\s\*Base directory for this skill:"\)/,
               "the live stream twin — the always-expanded live note box is gone");
  // the payload rides skillMd with EMPTY content, so judge/caption text readers never see it
  assert.match(EM, /"message": \{"role": "assistant", "content": \[\], "stop_reason": None\}/);
});
