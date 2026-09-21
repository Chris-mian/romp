// The bundles' read of the shell's source check (plans/panes-as-data.md, section 5): fail-closed. No check on the page
// refuses; the check's true admits; anything else, a non-boolean answer or a throw, refuses.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { paneSourceOk } from "./pane-source";

test("paneSourceOk: no check refuses, true admits, anything else refuses", () => {
  const e = { source: {}, origin: "http://TESTHOST:7432", data: { romp: "openKeys" } } as unknown as MessageEvent;
  const win = (f: unknown) => ({ __rompPaneSourceOk: f }) as unknown as Window;
  assert.equal(paneSourceOk(e, win(undefined)), false, "a page without the shell's check: nothing is acted on");
  assert.equal(paneSourceOk(e, win(() => true)), true, "the check's true admits");
  assert.equal(paneSourceOk(e, win(() => false)), false);
  assert.equal(paneSourceOk(e, win(() => "yes")), false, "only the boolean true");
  assert.equal(paneSourceOk(e, win(() => { throw new Error("x"); })), false, "a throwing check refuses");
  let seen: unknown = null;
  paneSourceOk(e, win((ev: MessageEvent) => { seen = ev; return true; }));
  assert.equal(seen, e, "the event itself is handed to the check");
});
