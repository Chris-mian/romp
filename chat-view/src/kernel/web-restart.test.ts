// Cache policy (web-restart.ts). HTML + bundles are served no-store so a kernel restart actually
// surfaces new code. (The Restart button itself moved into the timeline controls row — see
// timeline-render.test.ts; it POSTs the kernel's same-origin /restart, which relays to the manager.)
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { NO_STORE } from "./web-restart";

test("NO_STORE carries a no-store Cache-Control (so a restart surfaces the new bundle)", () => {
  assert.equal(NO_STORE["Cache-Control"], "no-store");
});
