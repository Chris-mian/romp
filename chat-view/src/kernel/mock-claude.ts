// mock-claude — test-only helper that materializes a scriptable `claude`
// imposter for backend tests: a Node script speaking the CLI's stream-json
// protocol, driven by a scenario file instead of a model.
//
// Event shapes are pinned from live probes of the real CLI (2026-06-12,
// claude_code_version 2.1.175), exercised by mock-claude.test.ts:
//   input :  {"type":"user","message":{"role":"user","content":[{type:"text",…}]}}
//   intr  :  {"type":"control_request","request_id":R,"request":{"subtype":"interrupt"}}
//            → ack {"type":"control_response","response":{"subtype":"success","request_id":R}}
//            → result subtype "error_during_execution", terminal_reason "aborted_streaming"
//   output:  system:init (re-emitted EVERY turn; carries session_id, model,
//            permissionMode, cwd) · assistant/user messages (content blocks
//            text / tool_use{id,name,input} / tool_result{tool_use_id,content,
//            is_error}) · result{subtype,is_error,result,stop_reason,
//            terminal_reason,num_turns,usage,…}
//   life  :  ONE session_id for the whole process (interrupts included);
//            process exits when stdin closes. `--resume <id>` forks a NEW
//            session_id (matching interactive resume).
//
// Scenarios are SYNTHETIC by construction — never paste real prompts,
// transcripts, or identifiers into one (CLAUDE.md privacy rule, enforced by
// tests/test_no_personal_identifiers.py).
//
// Timing in scenarios is event-based, not sleep-based: a `gate` step makes the
// actor wait for a file to exist, so a test can hold a turn open (to interrupt
// it, to observe "working") and release it deterministically.
import * as fs from "fs";
import * as path from "path";

export type MockStep =
  | { kind: "text"; text: string }
  | { kind: "tool"; name: string; input: unknown; result: string; isError?: boolean }
  | { kind: "gate"; file: string }   // wait until this file exists
  | { kind: "delay"; ms: number }    // last resort; prefer gate
  | { kind: "crash"; code?: number }; // die mid-turn, no result event (crash test)

export interface MockTurn {
  steps?: MockStep[];
  resultText?: string;   // result.result (default "ok")
  isError?: boolean;     // emit an error result (subtype error_during_execution)
}

export interface MockScenario {
  sessionId: string;       // session_id when not overridden by --session-id
  forkSessionId?: string;  // session_id when launched with --resume (default "fork-" + resumed id)
  turns: MockTurn[];       // turn k of the process plays turns[min(k, last)]
}

// The imposter itself. Kept as a plain-JS template (it runs under `node`, not
// the test runner). Reads its scenario from <its dir>/scenario.json at every
// turn, so tests may rewrite the scenario file mid-run.
const ACTOR_JS = `#!/usr/bin/env node
"use strict";
const fs = require("fs");
const path = require("path");
const DIR = __dirname;
fs.appendFileSync(path.join(DIR, "claude-calls.log"), "claude " + process.argv.slice(2).join(" ") + "\\n");

const argv = process.argv.slice(2);
const argOf = (flag) => { const i = argv.indexOf(flag); return i >= 0 ? argv[i + 1] : null; };
const scenario = () => JSON.parse(fs.readFileSync(path.join(DIR, "scenario.json"), "utf8"));

const s0 = scenario();
const resumed = argOf("--resume");
const SID = argOf("--session-id") || (resumed ? (s0.forkSessionId || "fork-" + resumed) : s0.sessionId);
const MODEL = argOf("--model") || "mock-model-1";
let turnIdx = 0;
let interrupted = false;

const emit = (o) => process.stdout.write(JSON.stringify(o) + "\\n");
const init = () => emit({ type: "system", subtype: "init", cwd: process.cwd(), session_id: SID,
  model: MODEL, permissionMode: "default", claude_code_version: "mock", uuid: "u-init-" + turnIdx });
const usage = () => ({ input_tokens: 7, output_tokens: 11, cache_creation_input_tokens: 0, cache_read_input_tokens: 0 });
const result = (turn, ok) => emit({ type: "result",
  subtype: ok ? "success" : "error_during_execution", is_error: !ok,
  result: ok ? (turn.resultText || "ok") : undefined,
  stop_reason: ok ? "end_turn" : "tool_use",
  terminal_reason: ok ? "completed" : "aborted_streaming",
  num_turns: 1, duration_ms: 5, total_cost_usd: 0, usage: usage(), session_id: SID, uuid: "u-res-" + turnIdx });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function waitForFile(f) {
  for (;;) {
    if (interrupted) return;
    try { fs.statSync(f); return; } catch { /* not yet */ }
    await sleep(20);
  }
}

async function playTurn() {
  const sc = scenario();
  const turn = sc.turns[Math.min(turnIdx, sc.turns.length - 1)] || {};
  // NOTE: "interrupted" is a LATCH, consumed (cleared) only when a turn aborts
  // on it — never reset at turn start. An interrupt that lands in the gap
  // after a user message is written but before its turn begins still aborts
  // that turn (Esc semantics: the queued turn dies too). Resetting here would
  // silently lose such interrupts and leave gated scenarios waiting forever.
  init();
  if (interrupted) { result(turn, false); interrupted = false; turnIdx++; return false; }
  let toolN = 0;
  for (const step of turn.steps || []) {
    if (interrupted) break;
    if (step.kind === "gate") { await waitForFile(step.file); continue; }
    if (step.kind === "delay") { await sleep(step.ms); continue; }
    if (step.kind === "crash") { process.exit(step.code === undefined ? 9 : step.code); }
    if (step.kind === "text") {
      emit({ type: "assistant", message: { role: "assistant", model: MODEL,
        content: [{ type: "text", text: step.text }], usage: usage() }, session_id: SID, uuid: "u-t-" + turnIdx + "-" + toolN });
    } else if (step.kind === "tool") {
      const id = "toolu_mock_" + turnIdx + "_" + toolN++;
      emit({ type: "assistant", message: { role: "assistant", model: MODEL,
        content: [{ type: "tool_use", id, name: step.name, input: step.input }], usage: usage() }, session_id: SID, uuid: "u-tu-" + id });
      emit({ type: "user", message: { role: "user",
        content: [{ type: "tool_result", tool_use_id: id, content: step.result, is_error: !!step.isError }] }, session_id: SID, uuid: "u-tr-" + id });
    }
  }
  const ok = !interrupted && !turn.isError;
  result(turn, ok);
  interrupted = false;   // latch consumed (or no-op) — never leaks into the next turn
  turnIdx++;
  return ok;
}

// ---- single-shot print mode: claude -p "prompt" ----
const pIdx = argv.indexOf("-p");
const positionalPrompt = pIdx >= 0 && argv[pIdx + 1] && !argv[pIdx + 1].startsWith("-") ? argv[pIdx + 1] : null;
const inputFmt = argOf("--input-format");
const outputFmt = argOf("--output-format");

if (positionalPrompt && inputFmt !== "stream-json") {
  const sc = scenario();
  const turn = sc.turns[0] || {};
  if (outputFmt === "stream-json") {
    playTurn().then(() => process.exit(turn.isError ? 1 : 0));
  } else {
    // --output-format json: the single result object only (old headless mode)
    emit({ type: "result", subtype: turn.isError ? "error_during_execution" : "success",
      is_error: !!turn.isError, result: turn.resultText || "ok", num_turns: 1,
      session_id: SID, usage: usage() });
    process.exit(turn.isError ? 1 : 0);
  }
} else {
  // ---- stream-json input mode: turns arrive on stdin, one process, one SID ----
  let buf = "";
  let playing = Promise.resolve();
  let lastOk = true;
  process.stdin.on("data", (d) => {
    buf += String(d);
    let i;
    while ((i = buf.indexOf("\\n")) >= 0) {
      const line = buf.slice(0, i); buf = buf.slice(i + 1);
      if (!line.trim()) continue;
      let msg; try { msg = JSON.parse(line); } catch { continue; }
      if (msg.type === "user") {
        playing = playing.then(() => playTurn()).then((ok) => { lastOk = ok; });
      } else if (msg.type === "control_request" && msg.request && msg.request.subtype === "interrupt") {
        interrupted = true;
        emit({ type: "control_response", response: { subtype: "success", request_id: msg.request_id } });
        lastOk = false;
      }
    }
  });
  process.stdin.on("end", () => { playing.then(() => process.exit(lastOk ? 0 : 1)); });
}
`;

// Write the imposter + scenario into `dir`; returns the executable's path.
// `dir` is created if needed; rewrite the scenario later with writeScenario().
export function writeMockClaude(dir: string, scenario: MockScenario): string {
  fs.mkdirSync(dir, { recursive: true });
  const bin = path.join(dir, "claude");
  fs.writeFileSync(bin, ACTOR_JS);
  fs.chmodSync(bin, 0o755);
  writeScenario(dir, scenario);
  return bin;
}

export function writeScenario(dir: string, scenario: MockScenario): void {
  const f = path.join(dir, "scenario.json");
  fs.writeFileSync(f + ".tmp", JSON.stringify(scenario, null, 1));
  fs.renameSync(f + ".tmp", f);
}

// The argv log the imposter appends to (one line per invocation).
export function mockCalls(dir: string): string[] {
  try {
    return fs.readFileSync(path.join(dir, "claude-calls.log"), "utf8").trim().split("\n").filter(Boolean);
  } catch { return []; }
}
