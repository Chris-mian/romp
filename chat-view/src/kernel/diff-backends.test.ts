// LIVE DIFFERENTIAL RUNNER — the same scenario through the TMUX backend (a
// real tmux pane running the Claude Code TUI) and the STREAM backend (one
// long-lived stream-json process), compared structurally at the
// SessionBackend seam and in the transcripts both engines write.
//
// SKIPPED unless ROMP_DIFF_LIVE=1: it spends real turns, spawns two
// briefly-visible sessions in the live fleet (diffprobe-*), and needs a
// running tmux server + the romp launcher on the login PATH.
//
//   ROMP_DIFF_LIVE=1 node --test out-tests/kernel/diff-backends.test.js
//
// The scenario is TEXT-ONLY on purpose: tool use enters the permission flow,
// which the substrates surface differently BY DESIGN (tmux: TUI picker
// mirrored via capture-pane; stream/-p: settings-driven auto-allow/deny until
// a canUseTool control path lands). That's a documented non-equivalence to
// test per-feature, not via raw diff.
//
// What equivalence means here:
//   - seam: each turn drives the same state cycle (working → settled) and the
//     session ends settled — enforced by the event waits themselves
//   - transcript: same turn count, same user texts, same exact replies, zero
//     tool_use on both sides
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { test } from "node:test";
import * as assert from "node:assert/strict";
import type { SessionBackend } from "./backend";
import { TmuxBackend } from "./tmux-backend";
import { StreamBackend } from "./stream-backend";

const LIVE = process.env.ROMP_DIFF_LIVE === "1";

const PROMPTS = ["Reply with exactly: ALPHA", "Reply with exactly: BRAVO"];
const REPLIES = ["ALPHA", "BRAVO"];

const NAMES_DIR = path.join(
  process.env.XDG_STATE_HOME || path.join(os.homedir(), ".local", "state"),
  "romp", "names",
);

interface Turn { prompt: string; reply: string; tools: string[] }
interface Trace { backend: string; states: string[]; turns: Turn[] }

const norm = (s: string) => (s === "working" ? "working" : "idle");

async function poll<T>(what: string, capMs: number, fn: () => T | null): Promise<T> {
  const t0 = Date.now();
  for (;;) {
    const v = fn();
    if (v != null) return v;
    if (Date.now() - t0 > capMs) throw new Error("timed out waiting for: " + what);
    await new Promise((r) => setTimeout(r, 500));
  }
}

function sidByName(name: string): string | null {
  try {
    for (const f of fs.readdirSync(NAMES_DIR)) {
      try {
        if (fs.readFileSync(path.join(NAMES_DIR, f), "utf8").split("\t")[0] === name) return f;
      } catch { /* race */ }
    }
  } catch { /* no names dir */ }
  return null;
}

// ~/.claude/projects/<key>/<sid>.jsonl — the key is the cwd with separators
// dashed; the two engines may record /tmp vs its /private/tmp realpath.
function transcriptOf(sid: string): string | null {
  const rec = (() => { try { return fs.readFileSync(path.join(NAMES_DIR, sid), "utf8").split("\t")[1] || ""; } catch { return ""; } })();
  const dirs = new Set([rec, (() => { try { return fs.realpathSync(rec); } catch { return rec; } })()]);
  for (const d of dirs) {
    const key = d.replace(/[/.]/g, "-");
    const f = path.join(os.homedir(), ".claude", "projects", key, sid + ".jsonl");
    if (fs.existsSync(f)) return f;
  }
  return null;
}

function turnsOf(file: string): Turn[] {
  const turns: Turn[] = [];
  let cur: Turn | null = null;
  for (const line of fs.readFileSync(file, "utf8").split("\n")) {
    if (!line.trim()) continue;
    let o: any; try { o = JSON.parse(line); } catch { continue; }
    const content = o?.message?.content;
    if (o.type === "user") {
      const text = typeof content === "string"
        ? content
        : Array.isArray(content) ? content.filter((c: any) => c?.type === "text").map((c: any) => c.text).join("") : "";
      if (text && !text.startsWith("<")) { cur = { prompt: text, reply: "", tools: [] }; turns.push(cur); }
    } else if (o.type === "assistant" && cur && Array.isArray(content)) {
      for (const c of content) {
        if (c?.type === "text" && c.text) cur.reply = c.text.trim();
        else if (c?.type === "tool_use" && c.name) cur.tools.push(c.name);
      }
    }
  }
  return turns;
}

async function runScenario(b: SessionBackend, label: string, name: string): Promise<Trace> {
  const states: string[] = [];
  const see = (s: string) => { const n = norm(s); if (states[states.length - 1] !== n) states.push(n); };
  assert.equal(await b.spawn(name, "/tmp"), true, label + ": spawn");
  // booted = the backend reports the session settled (tmux: hooks have run;
  // stream: registry written) — the composer/input channel is ready
  await poll(label + " boot", 60_000, () => {
    const st = b.liveSessions().get(name);
    return st && st.state && st.state !== "working" ? st : null;
  });
  see("idle");
  for (const prompt of PROMPTS) {
    assert.equal(b.send(name, prompt), true, label + ": send");
    await poll(label + " working", 30_000, () => b.liveSessions().get(name)?.state === "working" ? true : null);
    see("working");
    await poll(label + " settled", 150_000, () => {
      const s = b.liveSessions().get(name)?.state;
      return s && s !== "working" ? true : null;
    });
    see("idle");
  }
  const sid = await poll(label + " sid", 10_000, () => sidByName(name));
  const file = await poll(label + " transcript", 20_000, () => transcriptOf(sid));
  // the transcript flushes asynchronously — wait for both replies on disk
  const turns = await poll(label + " turns on disk", 30_000, () => {
    const t = turnsOf(file).filter((x) => PROMPTS.includes(x.prompt));
    return t.length === PROMPTS.length && t.every((x) => x.reply) ? t : null;
  });
  return { backend: label, states, turns };
}

test("differential: tmux and stream backends behave equivalently on a text scenario", { skip: !LIVE, timeout: 600_000 }, async () => {
  const run = Math.floor(Date.now() / 1000).toString(36);
  const cases: Array<[SessionBackend, string, string]> = [
    [new TmuxBackend(), "tmux", `diffprobe-t-${run}`],
    [new StreamBackend(), "stream", `diffprobe-s-${run}`],
  ];
  const traces: Trace[] = [];
  try {
    for (const [b, label, name] of cases) traces.push(await runScenario(b, label, name));
  } finally {
    for (const [b, , name] of cases) { try { b.kill(name); } catch { /* gone */ } }
  }
  const [tmux, stream] = traces;
  console.log("tmux  :", tmux.states.join(" → "), JSON.stringify(tmux.turns));
  console.log("stream:", stream.states.join(" → "), JSON.stringify(stream.turns));

  // seam: identical normalized state cycles
  assert.deepEqual(stream.states, tmux.states, "state cycles diverge");
  // transcript structure: same prompts in order, exact same replies, no tools
  assert.deepEqual(tmux.turns.map((t) => t.prompt), PROMPTS);
  assert.deepEqual(stream.turns.map((t) => t.prompt), PROMPTS);
  assert.deepEqual(tmux.turns.map((t) => t.reply), REPLIES, "tmux replies");
  assert.deepEqual(stream.turns.map((t) => t.reply), REPLIES, "stream replies");
  assert.deepEqual(tmux.turns.flatMap((t) => t.tools), [], "tmux used tools");
  assert.deepEqual(stream.turns.flatMap((t) => t.tools), [], "stream used tools");
});
