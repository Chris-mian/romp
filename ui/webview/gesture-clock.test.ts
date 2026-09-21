// The gesture clock (ui/webview/gesture-clock.js), exercised for real. Every kernel-setting
// message stamps `gt` through it, and the kernel orders each store's applies by that stamp
// (tests/test_setting_gesture_order.py) — so the stamp used to be the device's bare wall clock, and
// a laptop ten minutes ahead locked every correctly-clocked device out of a setting for ten
// minutes (no gesture from them could outrank the future stamp it had stored). The clock is a
// per-store logical clock seeded by the wall clock: it learns the stamps the kernel reports
// (/version's settingsGt, a settingStale frame's storedGt) and stamps above the highest it has
// seen. BEHAVIORAL: the module is required and driven with Date.now stubbed — no source pins.
// Module state is per bundle, so each test uses store names of its own.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const { learn, learnAll, stamp } = require("./gesture-clock.js");

/** Run `fn` with Date.now pinned to `now` (or to a sequence of values); always restored. */
function withNow<T>(now: number | number[], fn: () => T): T {
  const real = Date.now;
  const seq = Array.isArray(now) ? [...now] : [now];
  Date.now = () => (seq.length > 1 ? seq.shift()! : seq[0]);
  try { return fn(); } finally { Date.now = real; }
}

test("with nothing learned, the stamp is the wall clock", () => {
  assert.equal(withNow(5000, () => stamp("t1-store")), 5000);
});

test("a learned stamp at or above the wall clock lifts the next stamp to learned + 1", () => {
  learn("t2-store", 9000);                       // a store stamped by a device whose clock ran ahead
  assert.equal(withNow(5000, () => stamp("t2-store")), 9001, "above the future stamp, not the wall clock");
  learn("t2-store", 9001);                       // exactly what the clock already holds — no lift
  assert.equal(withNow(5000, () => stamp("t2-store")), 9002, "still strictly increasing");
});

test("a learned stamp below the wall clock changes nothing — the wall clock already outranks it", () => {
  learn("t3-store", 100);
  assert.equal(withNow(5000, () => stamp("t3-store")), 5000);
});

test("two stamps within one millisecond are strictly increasing (no equal-stamp collision)", () => {
  const [a, b, c] = withNow(7000, () => [stamp("t4-store"), stamp("t4-store"), stamp("t4-store")]);
  assert.deepEqual([a, b, c], [7000, 7001, 7002]);
});

test("a wall clock that steps back cannot lower the clock: stamps stay above every stamp minted here", () => {
  const a = withNow(8000, () => stamp("t5-store"));
  const b = withNow(7000, () => stamp("t5-store"));   // NTP correction between two clicks
  assert.equal(a, 8000);
  assert.equal(b, 8001, "the second click still orders after the first");
});

test("stamps are per store: learning one store's stamp lifts no other", () => {
  learn("t6-judge", 9_000_000);
  assert.equal(withNow(5000, () => stamp("t6-nudge")), 5000, "another store's clock is untouched");
  assert.equal(withNow(5000, () => stamp("t6-judge")), 9_000_001);
});

test("learn ignores garbage: a lower stamp, zero, NaN, a non-number, an empty or non-string store", () => {
  learn("t7-store", 6000);
  learn("t7-store", 5999);                        // lower — ignored
  learn("t7-store", 0);
  learn("t7-store", NaN);
  learn("t7-store", "not a number");
  learn("t7-store", Infinity);
  learn("t7-store", null);
  learn("t7-store", undefined);
  learn("", 10_000_000);                          // no store name — ignored, and nothing else is lifted
  learn(42 as any, 10_000_000);
  learn(null as any, 10_000_000);
  assert.equal(withNow(1000, () => stamp("t7-store")), 6001, "only the valid 6000 moved the clock");
  assert.equal(withNow(1000, () => stamp("")), 1000, "the empty name learned nothing");
});

test("learn takes a numeric string too (a kernel that serialized the int as text)", () => {
  learn("t8-store", "7000" as any);
  assert.equal(withNow(1000, () => stamp("t8-store")), 7001);
});

test("learnAll folds a /version settingsGt dict and ignores anything that is not a plain object", () => {
  learnAll({ "t9-a": 4000, "t9-b": 0, "t9-c": "x", "t9-d": 3000 });
  assert.equal(withNow(1000, () => stamp("t9-a")), 4001);
  assert.equal(withNow(1000, () => stamp("t9-b")), 1000, "0 taught nothing");
  assert.equal(withNow(1000, () => stamp("t9-c")), 1000, "a non-number taught nothing");
  assert.equal(withNow(1000, () => stamp("t9-d")), 3001);
  for (const bad of [undefined, null, 7, "gt", [5000], true])   // an older kernel sends no dict at all
    assert.doesNotThrow(() => learnAll(bad));
  assert.equal(withNow(1000, () => stamp("0")), 1000, "an array's index never became a store");
});

test("the maintainer's scenario end to end: a future stamp learned from a refusal is outranked by the next click", () => {
  // a laptop ten minutes ahead stamped the store at T+600s; this correctly-clocked device's click at
  // T is refused, the frame reports storedGt, and the re-issue must climb above it
  const T = 1_700_000_000_000, skew = 600_000;
  const first = withNow(T, () => stamp("t10-judge"));
  assert.equal(first, T, "the first click knows nothing and trusts the wall clock");
  learn("t10-judge", T + skew);                   // the settingStale frame's storedGt
  const retry = withNow(T + 1, () => stamp("t10-judge"));
  assert.equal(retry, T + skew + 1, "Apply anyway stamps above the future stamp, not ten minutes later");
});

test("every gt emitter under ui/webview stamps through this module (the sources load it)", () => {
  const dir = path.resolve(process.cwd(), "..", "ui", "webview");
  for (const f of ["gear.js", "feed.ts", "file-view.ts"])
    assert.ok(/require\(['"]\.\/gesture-clock\.js['"]\)/.test(fs.readFileSync(path.join(dir, f), "utf8")),
      `${f} requires the gesture clock`);
});
