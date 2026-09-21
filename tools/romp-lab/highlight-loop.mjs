// The scripted highlight loop (T106): drive the REAL dashboard through the user's exact flow and
// assert the comment-mark state at every event boundary of the T102 contract. Synthetic content
// only. Exits non-zero naming the first diverging phase, so a fix → re-run cycle loops cleanly.
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const require2 = createRequire(path.join(ROOT, "vscode-extension", "package.json"));
const { chromium } = require2("playwright");

const PORT = process.env.PORT, TOKEN = process.env.TOKEN, LAB = process.env.LAB_DIR, PROJ = process.env.PROJECT_DIR;
const MODEL = process.env.LAB_MODEL || "Haiku";
// The anchor turn is RICH on purpose (T152, the user 2026-08-28: a comment on a long turn with
// bold sections, links and an inline image rendered a floating quote over a blank thread): the
// model echoes markdown — bold + inline code + a path + an image — so the passage's rendered text
// SPANS ELEMENT BOUNDARIES and the exact-match re-find, the selection, and the quote all exercise
// the hard case. PASSAGE is the RENDERED (plain) text the user would drag over.
const PASSAGE_MD = "the **moon** has `no weather` to speak of (notes: /tmp/moon-notes.txt)";
const PASSAGE = "the moon has no weather to speak of (notes: /tmp/moon-notes.txt)";
const TURN_MD = PASSAGE_MD + "\n\n![plot](/tmp/moon-plot.png)";
const shots = path.join(LAB, "shots");
let phaseN = 0;
const fails = [];

const b = await chromium.launch();
const page = await b.newPage({ viewport: { width: 1280, height: 850 } });
page.on("pageerror", (e) => console.log("PAGEERR", String(e)));
const shot = async (name) => page.screenshot({ path: path.join(shots, `${String(++phaseN).padStart(2, "0")}-${name}.png`) });
const busy = () => page.evaluate(() => !!document.querySelector("mark.cmt-hl.busy"));
const marked = () => page.evaluate(() => !!document.querySelector("mark.cmt-hl"));
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " — " + detail : ""}`);
  if (!ok) fails.push(name);
};
// continuous flicker sampling between two moments: the pulse must not blip through thread-open
let flickerStop = null;
const sampleFlicker = () => {
  const seen = { falses: 0, samples: 0 };
  const t = setInterval(async () => {
    try { seen.samples++; if (!(await busy())) seen.falses++; } catch { /* page busy */ }
  }, 60);
  flickerStop = () => { clearInterval(t); return seen; };
};

await page.goto(`http://127.0.0.1:${PORT}/chat?token=${TOKEN}`);
await page.waitForSelector("#composer-input", { timeout: 20000 });

// ── create the lab session through the + picker, exactly as a user would ──
await page.click(".tab.tab-add", { timeout: 8000 });
await page.waitForSelector("#picker-search", { timeout: 8000 });
await shot("picker");
await page.fill("#picker-search", "lab-moon");
await page.fill("#picker-dir", PROJ);
await page.click("#picker-new-btn");
await page.waitForSelector(".tab", { timeout: 30000 });
// T151, permanent: the SERVED chat page (THEME_CSS vars defined — the exact context the T141
// harness missed) paints the strip on the page dark; the tokens' fallbacks are dead code here.
{
  const t = await page.evaluate(() => ({
    strip: getComputedStyle(document.getElementById("tabbar")).backgroundColor,
    page: getComputedStyle(document.body).backgroundColor,
  }));
  check("0-strip-is-page-dark-when-served", t.strip === t.page, `strip ${t.strip} vs page ${t.page}`);
}
// wait until the session is REAL (composer live, statusline shows a state chip)
await page.waitForSelector("#statusline .chip, #statusline .compacting-line", { timeout: 60000 });
await shot("session-open");

// ── drop the model to the lab default (cheapest) via the statusline menu ──
await page.waitForSelector('#statusline .meta-btn[data-kind="model"]', { timeout: 60000 });
const dropped = await page.evaluate(async (want) => {
  const btn = document.querySelector('#statusline .meta-btn[data-kind="model"]');
  if (!btn) return "no-model-badge";
  btn.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 200));
  const item = Array.from(document.querySelectorAll(".meta-menu .meta-item"))
    .find((i) => i.textContent.toLowerCase().includes(want.toLowerCase()));
  if (!item) return "no-menu-item";
  item.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  return "ok";
}, MODEL);
console.log("model drop:", dropped);
// bypass permissions in the HERMETIC lab so the thread's tool step never parks on an ask — the
// thread inherits the parent's mode at fork, and the clear-timing phase needs a real tool pause
const moded = await page.evaluate(async () => {
  const btn = document.querySelector('#statusline .meta-btn[data-kind="mode"]');
  if (!btn) return "no-mode-badge";
  btn.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 200));
  const item = Array.from(document.querySelectorAll(".meta-menu .meta-item"))
    .find((i) => i.textContent.toLowerCase().includes("bypass"));
  if (!item) return "no-bypass-item";
  item.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  return "ok";
});
console.log("mode bypass:", moded);

// ── a REAL turn: ask for a stable, selectable sentence ──
await page.fill("#composer-input", `Reply with exactly this markdown and nothing else (verbatim, keep all formatting characters): ${TURN_MD}`);
await page.keyboard.press("Enter");
await page.waitForFunction((p) => Array.from(document.querySelectorAll(".turn-assistant .md"))
  .some((e) => e.textContent.includes(p)), PASSAGE, { timeout: 180000 });
await shot("reply-landed");

// ── the COMMENT flow: select the passage → context menu → Comment → send ──
await page.evaluate((p) => {
  // cross-node selection (T152): the rich turn splits the passage across <strong>/<code>/link text
  // nodes — walk the text nodes accumulating rendered text, and set the range ends INSIDE the
  // nodes where the passage starts and ends, exactly as a user's drag would land
  const el = Array.from(document.querySelectorAll(".turn-assistant .md")).find((e) => e.textContent.includes(p));
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  const nodes = []; let all = "";
  let tn; while ((tn = walker.nextNode())) { nodes.push({ n: tn, at: all.length }); all += tn.data; }
  const start = all.indexOf(p);
  const end = start + p.length;
  const locate = (pos, isEnd) => {
    for (let i = nodes.length - 1; i >= 0; i--) {
      const { n, at } = nodes[i];
      if (pos > at || (pos === at && (!isEnd || i === 0))) return [n, pos - at];
      if (pos === at && isEnd) return [nodes[i - 1].n, nodes[i - 1] ? pos - nodes[i - 1].at : 0];
    }
    return [nodes[0].n, 0];
  };
  const [sn, so] = locate(start, false);
  const [en, eo] = locate(end, true);
  const r = document.createRange();
  r.setStart(sn, so); r.setEnd(en, eo);
  const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
  document.dispatchEvent(new Event("selectionchange"));
  el.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true, clientX: 420, clientY: 300 }));
}, PASSAGE);
await page.waitForSelector(".ctx-menu", { timeout: 5000 });
await page.evaluate(() => {
  for (const it of document.querySelectorAll(".ctx-menu .ctx-item")) if (it.textContent === "Comment") it.dispatchEvent(new MouseEvent("click", { bubbles: true }));
});
await page.waitForSelector(".cmt-pop .cmt-input", { timeout: 5000 });
await page.fill(".cmt-pop .cmt-input", "Why is that the case? One short sentence.");
const preSend = await busy();
await page.keyboard.press("Enter");
// PHASE 1: the send gesture latches the pulse IMMEDIATELY — before any thread exists
await page.waitForTimeout(250);
check("1-latch-at-send", (await busy()) === true, `pre-send busy was ${preSend}`);
await shot("send-latched");
sampleFlicker();

// T152, permanent: the open popover NEVER renders a blank conversation area — at every sample it
// shows the loader, pending sends, or content (the live specimen blanked for 200+s while a 40MB
// fork booted across restarts). Sampled through the whole thread-open window below.
const blankSamples = { blank: 0, total: 0 };
const blankTimer = setInterval(async () => {
  try {
    blankSamples.total++;
    const st = await page.evaluate(() => {
      const msgs = document.querySelector(".cmt-pop .cmt-msgs");
      return msgs ? msgs.children.length : -1;   // -1: popover closed (not a blank verdict)
    });
    if (st === 0) blankSamples.blank++;
  } catch { /* page busy */ }
}, 150);
// …and the QUOTE must carry the WHOLE selected passage, rich rendering notwithstanding
const quoteWhole = await page.evaluate((p) => {
  const q = document.querySelector(".cmt-pop .cmt-quote");
  return !!q && q.textContent.includes(p);
}, PASSAGE);
check("1b-whole-quote-on-rich-anchor", quoteWhole, "the quote block lost part of the cross-node passage");

// PHASE 2+3: hold through thread-open, clear exactly when the reply text renders in the popover
await page.waitForFunction(() => {
  const msgs = document.querySelector(".cmt-pop .cmt-msgs");
  return msgs && Array.from(msgs.querySelectorAll(".turn-assistant, .cmt-msg.agent"))
    .some((e) => e.textContent.trim().length > 0);
}, undefined, { timeout: 240000 });
const flick = flickerStop();
clearInterval(blankTimer);
check("2-no-flicker-through-thread-open", flick.falses === 0, `${flick.falses}/${flick.samples} false samples before the reply`);
check("2b-thread-open-never-blanks", blankSamples.blank === 0,
  `${blankSamples.blank}/${blankSamples.total} samples showed an EMPTY conversation area (T152's floating-quote blank)`);
await shot("reply-in-thread");
// the clear rides the same frame that rendered the reply — allow one push
await page.waitForFunction(() => !document.querySelector("mark.cmt-hl.busy"), undefined, { timeout: 12000 })
  .then(() => check("3-clear-on-reply-record", true))
  .catch(async () => check("3-clear-on-reply-record", false, "still busy 12s after the reply rendered"));
await shot("settled-yellow");

// PHASE 4 (T112's specimen shape, permanent): the follow-up forces an INTERIM text record, a real
// tool pause, then the final answer — the clear must wait for the reply to be VISIBLE, never firing
// on the interim record the way the specimen did.
const FINAL = "FINAL ANSWER: the moon is airless.";
await page.fill(".cmt-pop .cmt-input",
  "Do exactly this, in order: first reply with only the sentence 'checking the sources first.' — then run the bash command `echo verified` — then give a final message containing exactly this phrase: " + FINAL);
await page.keyboard.press("Enter");
await page.waitForTimeout(250);
check("4-follow-up-relatch", (await busy()) === true);
await shot("followup-latched");
// CLEAR-TIMING (permanent, T112): sample continuously — the mark may never read settled while the
// rendered thread lacks the final answer text (the reader's own view is the arbiter).
const violations = { count: 0, samples: 0 };
const timer = setInterval(async () => {
  try {
    violations.samples++;
    const st = await page.evaluate((f) => ({
      busy: !!document.querySelector("mark.cmt-hl.busy"),
      hasFinal: Array.from(document.querySelectorAll(".cmt-pop .cmt-msgs .turn-assistant"))
        .some((e) => e.textContent.includes(f)) }), FINAL);
    if (!st.busy && !st.hasFinal) violations.count++;
  } catch { /* page busy */ }
}, 100);
// FULL-TEXT (permanent, T112): the rendered thread must converge to the complete reply
await page.waitForFunction((f) => Array.from(document.querySelectorAll(".cmt-pop .cmt-msgs .turn-assistant"))
  .some((e) => e.textContent.includes(f)), FINAL, { timeout: 300000 })
  .then(() => check("4c-full-text-renders", true))
  .catch(() => check("4c-full-text-renders", false, "the final answer text never rendered in the thread"));
clearInterval(timer);
check("4d-clear-never-precedes-visible-reply", violations.count === 0,
  `${violations.count}/${violations.samples} samples read settled before the answer was visible`);
await page.waitForFunction(() => !document.querySelector("mark.cmt-hl.busy"), undefined, { timeout: 15000 })
  .then(() => check("4b-follow-up-clears-on-its-reply", true))
  .catch(async () => check("4b-follow-up-clears-on-its-reply", false, "still busy after the follow-up's reply"));
await shot("followup-settled");

// PHASE 4e (T138, permanent): a thread's running turn can be INTERRUPTED from the popover — the
// stop square renders beside the working chip, targets the THREAD's own session, the turn ends
// mid-stream, the pulse clears on the gesture (no reply record is coming), and the partial thread
// renders honestly (whatever landed stays; nothing poses as a full answer).
await page.fill(".cmt-pop .cmt-input",
  "Count slowly: write one line per number from 1 to 40, each on its own line, no tools.");
await page.keyboard.press("Enter");
await page.waitForTimeout(250);
check("4e-relatch-for-interrupt-run", (await busy()) === true);
// the stop affordance must appear with the working chip in the popover statusline
await page.waitForSelector('.cmt-pop .cmt-state .stop-btn[data-act="cmtinterrupt"]', { timeout: 60000 })
  .then(() => check("4e-stop-affordance-renders", true))
  .catch(() => check("4e-stop-affordance-renders", false, "no stop square in the popover's working state"));
await shot("interrupt-affordance");
// interrupt MID-STREAM: wait for streaming text to start, then click the popover's own stop
await page.waitForFunction(() => {
  const msgs = document.querySelector(".cmt-pop .cmt-msgs");
  return msgs && /\b3\b/.test(msgs.textContent || "");
}, undefined, { timeout: 120000 }).catch(() => null);
const hadStop = await page.evaluate(() => {
  const b = document.querySelector('.cmt-pop .cmt-state .stop-btn[data-act="cmtinterrupt"]');
  if (!b) return false;
  b.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  return true;
});
check("4e-stop-clicked", hadStop, "the stop square vanished before the click");
// the ack is instant: the chip flips to Interrupting… without waiting on the kernel
const acked = await page.evaluate(() => !!document.querySelector(".cmt-pop .cmt-state .chip-interrupting"));
check("4e-instant-ack", acked, "no Interrupting… chip right after the click");
// the pulse clears on the GESTURE — no reply record is coming; never hangs green
await page.waitForFunction(() => !document.querySelector("mark.cmt-hl.busy"), undefined, { timeout: 12000 })
  .then(() => check("4e-pulse-clears-on-interrupt", true))
  .catch(() => check("4e-pulse-clears-on-interrupt", false, "pulse still green after the interrupt"));
// the turn actually ENDS on the thread's CLI: the popover chip leaves working within a few pushes
await page.waitForFunction(() => !document.querySelector(".cmt-pop .cmt-state .chip-working"), undefined, { timeout: 60000 })
  .then(() => check("4e-turn-ends", true))
  .catch(() => check("4e-turn-ends", false, "thread still working 60s after the interrupt"));
await shot("interrupted-settled");

// PHASE 6 (T145, permanent): RELAY — the discussion goes back to the main conversation whole,
// machine-dressed, with staged feedback and a persistent sent-back marker; the thread stays
// talkable. Runs BEFORE phase 5's quiet sampling so its own settling is covered by it.
{
  const relayBtn = await page.evaluate(() => {
    const b = Array.from(document.querySelectorAll('.cmt-pop .cmt-act')).find((x) => x.textContent === "Relay");
    if (!b) return false;
    b.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    return true;
  });
  check("6-relay-button-renders-and-clicks", relayBtn, "no Relay button in the open popover");
  // instant ack: the button flips before any kernel round-trip
  const ack = await page.evaluate(() => {
    const b = Array.from(document.querySelectorAll('.cmt-pop .cmt-act')).find((x) => x.textContent === "Relaying…");
    return !!b && b.disabled;
  });
  check("6-instant-ack", ack, "the button did not flip to Relaying…");
  // the arrival: a machine-dressed (romp-attributed) turn in the MAIN thread carrying the WHOLE
  // exchange — both the user's question and the final answer text
  await page.waitForFunction((f) => Array.from(document.querySelectorAll("#content .turn.romp"))
    .some((t) => t.textContent.includes("side discussion") && t.textContent.includes(f)
              && t.textContent.includes("Why is that the case?")), FINAL, { timeout: 120000 })
    .then(() => check("6-machine-dressed-whole-exchange-arrives", true))
    .catch(() => check("6-machine-dressed-whole-exchange-arrives", false,
      "no romp-attributed arrival carrying both sides of the exchange in the main thread"));
  // the persistent sent-back marker in the thread, and the composer still invites more talk
  await page.waitForFunction(() => !!document.querySelector(".cmt-pop .cmt-relayed-note"), undefined, { timeout: 30000 })
    .then(() => check("6-sent-back-marker", true))
    .catch(() => check("6-sent-back-marker", false, "no ↩ sent-back marker in the popover"));
  const talkable = await page.evaluate(() => !!document.querySelector(".cmt-pop .cmt-input"));
  check("6-thread-stays-talkable", talkable, "the composer vanished after the relay");
  await shot("relayed");
}

// PHASE 5: nothing sticks — sample well past several pushes
await page.waitForTimeout(10000);
check("5-nothing-sticks", (await busy()) === false, "busy after 10s quiet");
check("mark-still-present", await marked(), "the settled yellow mark must remain");
await shot("final");

await b.close();
if (fails.length) { console.log("DIVERGED:", fails.join(", ")); process.exit(1); }
console.log("ALL PHASES GREEN");
