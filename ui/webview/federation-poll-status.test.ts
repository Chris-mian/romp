// The /tunnels poll's answer is the host list only when it is an OK answer (the master switch's follow-up, the four lows of
// its last read). A 5xx whose body parses as JSON (a proxy in JSON-error mode) used to read as "the list in hand, no hosts":
// hostsRead flipped true and the pane's absence-driven writers pruned every remote host's marks on the first frame. A non-ok
// answer throws now, so the catch returns with hostsRead standing; and a failing spell is filed once as a hostconn crumb, its
// end once, so a browser whose prunes never resume says why. The manager is built here under node with a stubbed fetch and a
// window that records what diag sends; poll is private in TypeScript and reached through any.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { FederationManager } from "./federation";

type Crumb = { type: string; surface: string; what: string; data: any };
function harness(answers: Array<() => Promise<any>>) {
  const crumbs: Crumb[] = [];
  (globalThis as any).window = { __rompLocalSend: (m: Crumb) => crumbs.push(m), dispatchEvent() { return true; }, addEventListener() {} };
  let i = 0;
  (globalThis as any).fetch = async () => { const a = answers[Math.min(i, answers.length - 1)]; i++; return a(); };
  const m = new FederationManager() as any;
  return { m, crumbs, polls: () => i };
}
const okEmpty = () => Promise.resolve({ ok: true, status: 200, json: async () => ({ tunnels: [] }) });
const badJson = () => Promise.resolve({ ok: false, status: 502, json: async () => ({ tunnels: [] }) });
const thrown = () => Promise.reject(new TypeError("network down"));

test("a non-ok /tunnels answer whose body parses leaves the host list unread, and is filed once as a failing spell", async () => {
  const { m, crumbs } = harness([badJson]);
  assert.equal(m.hostsRead, false);
  await m.poll();
  assert.equal(m.hostsRead, false, "a 502 with a JSON body is not the list in hand");
  await m.poll();
  assert.equal(m.hostsRead, false);
  const failing = crumbs.filter((c) => c.what === "hostconn" && c.data.ev === "tunnels-poll-failing");
  assert.equal(failing.length, 1, "the failing spell is filed once, not per poll");
  assert.match(failing[0].data.why, /HTTP 502/);
  assert.equal(failing[0].data.unread, true);
});

test("a fetch that throws is the same spell; the first OK answer ends it, reads the list and files the recovery once", async () => {
  const { m, crumbs } = harness([thrown, thrown, okEmpty, okEmpty]);
  await m.poll(); await m.poll();
  assert.equal(m.hostsRead, false);
  await m.poll();
  assert.equal(m.hostsRead, true, "an OK answer with no hosts is the list in hand");
  await m.poll();
  const evs = crumbs.filter((c) => c.what === "hostconn").map((c) => c.data.ev);
  assert.deepEqual(evs, ["tunnels-poll-failing", "tunnels-poll-recovered"], "one crumb per edge of the spell");
});

test("an OK answer from the start files nothing and reads the list at once", async () => {
  const { m, crumbs } = harness([okEmpty]);
  await m.poll();
  assert.equal(m.hostsRead, true);
  assert.deepEqual(crumbs.filter((c) => c.what === "hostconn"), []);
});
