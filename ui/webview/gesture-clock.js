// The gesture clock — where every kernel-setting message mints its `gt` (PR #879 follow-up).
// Gesture stamps order the kernel's settings stores (a stamp at or below the stored one stands
// down), and they used to be the device's bare wall clock: a laptop ten minutes ahead picked a
// judge model and stamped every store ten minutes into the future, so for ten minutes every pick
// from a correctly-clocked phone was refused and no gesture from it could win. The stamp is a
// per-store LOGICAL clock seeded by the wall clock now: stamp(store) = max(Date.now(), the
// highest stamp this page has seen for that store + 1). A page learns stamps from /version's
// settingsGt (the gear reads it on every open; the file viewer on its consent check) and from
// the settingStale frame that refuses a gesture (storedGt IS the number to climb above) — so a
// device whose clock runs behind still outranks every stamp it has seen. Event over clock: the
// user's gesture is the new information, and its stamp says only "after everything I know of".
// Plain CJS like gear.js — one module graph per document (the feed pane and the chat pane each
// load their own), bundled wherever it is required, no build-list entry.
var seen = {};   // store name → the highest stamp this page has seen for it (learned or minted)

// Record a stamp the kernel reported for `store` (from /version or a settingStale frame). Only a
// higher number moves the clock; garbage (a non-string store, 0, NaN, a non-number) is ignored, so
// an older kernel that sends nothing, or a malformed frame, can never lower or corrupt it.
function learn(store, gt) {
  gt = Number(gt);
  if (typeof store !== 'string' || !store || !(gt > 0) || !isFinite(gt)) return;
  if (gt > (seen[store] || 0)) seen[store] = gt;
}

// Fold a whole /version `settingsGt` dict; anything but a plain object is a no-op.
function learnAll(map) {
  if (!map || typeof map !== 'object' || Array.isArray(map)) return;
  for (var k in map) if (Object.prototype.hasOwnProperty.call(map, k)) learn(k, map[k]);
}

// The stamp for a gesture on `store`, minted at the click. Records its own result, so stamps are
// strictly increasing per store on this page even when the wall clock steps back, and two clicks
// on one setting within a millisecond no longer collide as an equal-stamp-different-value refusal.
function stamp(store) {
  var s = Math.max(Date.now(), (seen[store] || 0) + 1);
  seen[store] = s;
  return s;
}

module.exports = { learn: learn, learnAll: learnAll, stamp: stamp };
