// Held mail names BOTH ends of the exchange (the user 2026-07-29). The card used to read "from
// HOST:session — <gist>" in one grey run, with the recipient missing entirely, so you could not tell
// which of your sessions was about to receive the message. It now renders the route the way every other
// surface renders a federated name: "host:" as quiet metadata, the session name in its identity colour,
// an arrow between the two, and the gist on its own line. The decision dialog wears the same header, so
// opening a message never re-words who it is between. Source-pinned (no jsdom for the feed renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const UI = path.resolve(process.cwd(), "..", "ui", "webview");
const FEED = fs.readFileSync(path.join(UI, "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.join(UI, "feed.css"), "utf8");

test("one end of the route: quiet host, identity-coloured session name", () => {
  assert.match(FEED, /function quarWho\(host: string, name: string, known\?: string\): HTMLElement/);
  assert.match(FEED, /const h = el\("span", "host-prefix"\);/, "the SAME class every surface uses");
  assert.match(FEED, /const n = el\("span", "fq-name"\);/);
  assert.match(FEED, /n\.style\.color = color/);
});

test("the colour is looked up, never invented", () => {
  // a session with no cards here has no known colour; leaving it uncoloured is honest, and a made-up
  // one would be a lie about identity — colours ARE how sessions are told apart everywhere else
  assert.match(FEED, /const color = known \|\| sessionColors\.get\(host \? host \+ ":" \+ name : name\) \|\| sessionColors\.get\(name\)/);
  assert.match(FEED, /if \(color\) n\.style\.color = color/, "no colour → no style, not a default");
});

test("the colour index is built from the merged payload, keyed the way a peer addresses a session", () => {
  assert.match(FEED, /const sessionColors = new Map<string, string>\(\)/);
  assert.match(FEED, /sessionColors\.set\(a\.name, a\.color\.bg\)/);
  assert.match(FEED, /sessionColors\.set\(a\.sid\.slice\(0, c\) \+ ":" \+ a\.name, a\.color\.bg\)/,
    "a remote session is also indexed under its host, which is how the sender is addressed");
});

test("the recipient's host comes from the card's own kernel, falling back to this machine", () => {
  // a card built by a remote kernel arrives with a host-prefixed sid; a local one has none, and the
  // kernel supplies this machine's name on the payload so the receiving end can still be named
  assert.match(FEED, /const toHost = \(it\.sid && it\.sid\.indexOf\(":"\) > 0\) \? it\.sid\.slice\(0, it\.sid\.indexOf\(":"\)\) : feedSelfHost;/);
  assert.match(FEED, /if \(typeof m\.selfHost === "string" && m\.selfHost\) feedSelfHost = m\.selfHost;/);
});

test("a host romp cannot reach wears the same struck mark its tabs and lanes do", () => {
  assert.match(FEED, /if \(hostIsDown\(host \+ ":x"\)\) \{ h\.classList\.add\("off"\); h\.title = hostDownNote\(host \+ ":x"\); \}/);
});

test("the dialog header IS the card's route, with the same colours", () => {
  assert.match(FEED, /interface QuarEnd \{ host: string; name: string; color\?: string \}/);
  assert.match(FEED, /function showQuarantineDialog\(from: QuarEnd, to: QuarEnd, body: string,/);
  assert.match(FEED, /const route = \(\) => title\.replaceChildren\(/);
  assert.match(FEED, /quarWho\(from\.host, from\.name, from\.color\)/);
  assert.match(FEED, /quarWho\(to\.host, to\.name, to\.color\)/);
  // the deny step is a question, not a route — it says who is being denied in words
  assert.match(FEED, /Deny the message from \$\{sender\}\. Send a note back\?/);
});

test("the full body still lives in the dialog only, and both openings reach it", () => {
  assert.match(FEED, /const ends = \(\): \[QuarEnd, QuarEnd\] => \[/);
  assert.match(FEED, /qBody\.onclick = [\s\S]*?showQuarantineDialog\(\.\.\.ends\(\)/, "clicking the line opens it");
  assert.match(FEED, /a\._qDeny\.onclick = [\s\S]*?showQuarantineDialog\(\.\.\.ends\(\)/, "Deny goes through it too");
  assert.match(FEED, /view\.textContent = body/, "the whole message renders only there");
  assert.doesNotMatch(FEED, /qBody\.textContent = `from /, "the old one-run line is gone");
});

test("the route is two lines: who to who, then the gist, each on one line", () => {
  assert.match(CSS, /\.fq-who \{ white-space: nowrap; \}/);
  assert.match(CSS, /\.fq-name \{ font-weight: 600; \}/);
  assert.match(CSS, /\.fq-arrow \{ margin: 0 6px; opacity: 0\.6; \}/);
  assert.match(CSS, /\.fq-gist \{[\s\S]*?white-space: nowrap; overflow: hidden; text-overflow: ellipsis;/);
  // the card itself no longer clips the route away with the gist's ellipsis
  assert.doesNotMatch(CSS, /\.fask-qbody \{[^}]*white-space: nowrap/);
});
