import { test } from "node:test";
import assert from "node:assert";
import { markerLabel, chooseStamps } from "./time-marker";

// All epochs below are built from local-time components so the test is timezone-agnostic
// (markerLabel reads getHours()/getMinutes()/getDate() in local time, matching the browser).
const at = (y: number, mo: number, d: number, h: number, mi: number, s = 0) =>
  Math.floor(new Date(y, mo, d, h, mi, s).getTime() / 1000);

// "now" anchored so that 2026-06-12 is today.
const NOW = new Date(2026, 5, 12, 12, 0, 0).getTime();

test("markerLabel: first timed turn (no previous) shows HH:MM", () => {
  const r = markerLabel(at(2026, 5, 12, 11, 3), null, NOW);
  assert.deepEqual(r, { text: "11:03", day: false, hm: "11:03" });
});

test("markerLabel: a run of same-minute turns shows the stamp only on the first", () => {
  const first = at(2026, 5, 12, 11, 3, 5);
  const second = at(2026, 5, 12, 11, 3, 40); // same minute, later seconds
  assert.equal(markerLabel(first, null, NOW).text, "11:03");
  assert.equal(markerLabel(second, first, NOW).text, ""); // suppressed
});

test("markerLabel: a suppressed turn still carries its HH:MM in hm (for the spacing pass)", () => {
  const first = at(2026, 5, 12, 11, 3, 5);
  const second = at(2026, 5, 12, 11, 3, 40);
  const r = markerLabel(second, first, NOW);
  assert.equal(r.text, "");      // not shown by the minute rule
  assert.equal(r.hm, "11:03");   // but available to reveal
});

test("markerLabel: the stamp reappears when the minute changes", () => {
  const prev = at(2026, 5, 12, 11, 3, 50);
  const next = at(2026, 5, 12, 11, 4, 1);
  assert.deepEqual(markerLabel(next, prev, NOW), { text: "11:04", day: false, hm: "11:04" });
});

test("markerLabel: same HH:MM on a different day is NOT deduped", () => {
  const prev = at(2026, 5, 11, 11, 3); // yesterday 11:03
  const today = at(2026, 5, 12, 11, 3); // today 11:03
  assert.equal(markerLabel(today, prev, NOW).text, "11:03");
});

test("markerLabel: first turn of a past day shows the date, emphasised", () => {
  const prev = at(2026, 5, 10, 9, 0);
  const r = markerLabel(at(2026, 5, 11, 9, 0), prev, NOW); // 2026-06-11 = yesterday
  assert.deepEqual(r, { text: "Yesterday · 09:00", day: true, hm: "09:00" });
});

test("markerLabel: a past day within a week shows the weekday", () => {
  const r = markerLabel(at(2026, 5, 8, 14, 30), null, NOW); // 2026-06-08 is a Monday
  assert.equal(r.day, true);
  assert.equal(r.text, "Mon · 14:30");
});

test("markerLabel: a past day older than a week shows month + day", () => {
  const r = markerLabel(at(2026, 4, 20, 8, 5), null, NOW); // 2026-05-20
  assert.deepEqual(r, { text: "May 20 · 08:05", day: true, hm: "08:05" });
});

test("markerLabel: a new day still shows the date even when same minute as prev day", () => {
  const prev = at(2026, 5, 10, 11, 3); // older day, same HH:MM
  const r = markerLabel(at(2026, 5, 11, 11, 3), prev, NOW);
  assert.equal(r.day, true);
  assert.equal(r.text, "Yesterday · 11:03");
});

// --- chooseStamps: the vertical-space pass (oneRow = one-line-turn height) ---

test("chooseStamps: a hard stamp every row leaves nothing to reveal", () => {
  const ys = [0, 20, 40, 60];
  const hard = [true, true, true, true];
  assert.deepEqual(chooseStamps(ys, hard, 20, 6), [true, true, true, true]);
});

test("chooseStamps: within 6 rows of the last stamp, soft turns stay hidden", () => {
  // one hard stamp at the top, then 5 same-minute rows (20px each) → all within 6*20=120px
  const ys = [0, 20, 40, 60, 80, 100];
  const hard = [true, false, false, false, false, false];
  assert.deepEqual(chooseStamps(ys, hard, 20, 6), [true, false, false, false, false, false]);
});

test("chooseStamps: a soft turn past the 6-row gap is revealed, and the gap resets", () => {
  // rows every 20px; hard at 0. 120px (=6 rows) below it the gap is reached.
  const ys = [0, 20, 40, 60, 80, 100, 120, 140, 160, 180, 200, 220, 240];
  const hard = ys.map(() => false);
  hard[0] = true;
  const show = chooseStamps(ys, hard, 20, 6);
  // first reveal at y=120 (index 6), next at y=240 (index 12)
  const revealed = show.map((s, i) => (s ? i : -1)).filter((i) => i >= 0);
  assert.deepEqual(revealed, [0, 6, 12]);
});

test("chooseStamps: tall rows trip the space gap in fewer rows", () => {
  // one hard stamp, then two 70px-tall rows: 140px > 120px → the 2nd is revealed
  const ys = [0, 70, 140];
  const hard = [true, false, false];
  assert.deepEqual(chooseStamps(ys, hard, 20, 6), [true, false, true]);
});

test("chooseStamps: with no hard stamp anywhere, the very first row is revealed", () => {
  const ys = [0, 20, 40];
  const hard = [false, false, false];
  assert.deepEqual(chooseStamps(ys, hard, 20, 6), [true, false, false]);
});
