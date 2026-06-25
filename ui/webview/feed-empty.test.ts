// Inbox-zero empty state: when every card is cleared the feed shows the romp tri-color WORDMARK,
// centered (the user 2026-06-22; was the plain swirl square, and before that an otter / 🦫 emoji).
// It's the one unobtrusive home for the wordmark — visible only when there's nothing to act on. The
// image is a CSS background so the relative url() resolves under /media in BOTH hosts — the browser
// (kernel serves /media) and VS Code (media/ is a localResourceRoot); an <img src> relative path
// would not resolve in the VS Code webview. No jsdom harness for the feed, so — like
// feed-focus.test.ts — pin it at the source level.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("the inbox-zero state shows the romp tri-color wordmark, centered (no otters, no emoji)", () => {
  assert.match(CSS, /\.feed-empty \{[^}]*background-image: url\(\.\.\/media\/romp-wordmark\.png\)/);
  assert.match(CSS, /\.feed-empty \{[^}]*background-position: center center/);
  assert.match(CSS, /\.feed-empty \{[^}]*background-size: 100% auto/, "stretched to the full pane width (the user 2026-06-25)");
  assert.match(CSS, /\.feed-empty \{[^}]*opacity: 0\.75/, "the at-rest wordmark is faded to 75% (the user 2026-06-25)");
  assert.doesNotMatch(CSS, /romp-otter/, "the otter image is gone");
  assert.doesNotMatch(FEED, /feed-empty"\); e\.textContent = "/, "the empty state must not set emoji/text on the logo");
  assert.match(FEED, /el\("div", "feed-empty"\)/);
});

test("the empty state stays accessible (role + aria-label, since a background image has no alt)", () => {
  assert.match(FEED, /e\.setAttribute\("role", "img"\)/);
  assert.match(FEED, /e\.setAttribute\("aria-label", "inbox zero/);
});

test("the wordmark ships in the served + packaged media dir; the otter is gone", () => {
  assert.ok(fs.existsSync(path.resolve(process.cwd(), "media", "romp-wordmark.png")), "media/romp-wordmark.png must exist (kernel serves /media; .vscodeignore keeps media/)");
  assert.ok(!fs.existsSync(path.resolve(process.cwd(), "media", "romp-otter.png")), "the otter image was deleted (the user 2026-06-15)");
});

test("an EMPTY column shows nothing — no '—' placeholder, and the count chip is blank not '0' (the user 2026-06-25)", () => {
  // the per-column "—" empty placeholder is gone entirely (reconcileCol no longer appends it)
  assert.doesNotMatch(FEED, /feed-col-empty.*textContent = "—"/);
  assert.doesNotMatch(FEED, /e\.textContent = "—"/, "no dash placeholder for an empty column");
  // the count chip shows the number only when > 0; an empty column's chip is blank AND collapsed (display:none)
  assert.match(FEED, /elc\.textContent = n \? String\(n\) : "";/);
  assert.match(FEED, /elc\.style\.display = n \? "" : "none";/);
  assert.match(FEED, /setCount\(cols\.asksCount, buckets\.asks\.length\)/);
  assert.doesNotMatch(FEED, /asksCount\.textContent = String\(/, "the unconditional String(count) is gone");
});
