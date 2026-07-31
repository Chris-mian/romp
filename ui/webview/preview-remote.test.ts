// A FEDERATED session's preview bytes must come from the kernel that can read the disk the path
// names (the user 2026-07-31: mentioned plots on a remote session's chat never rendered — the
// <img> hit the LOCAL kernel's /file, which read the local disk and 404'd, and the thumb removed
// itself). fileUrl routes a host-prefixed sid through the local kernel's /remote/<host>/file relay
// (the HTTP twin of the /remote/<host>/ws splice) with the bare sid the remote kernel actually
// knows; a bare (local) sid keeps the plain /file path byte-for-byte, so the single-kernel case is
// untouched. Same-origin either way — viewed from the phone over `tailscale serve`, both routes
// still resolve against the kernel that served the page.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { fileUrl } from "./preview";

const UUID = "11111111-2222-3333-4444-555555555555";

test("a bare (local) sid keeps the plain /file route — the single-kernel path is untouched", () => {
  assert.equal(fileUrl("/tmp/plot.png", UUID),
               "/file?path=%2Ftmp%2Fplot.png&sid=" + UUID);
});

test("no sid at all: /file with just the path", () => {
  assert.equal(fileUrl("/tmp/plot.png"), "/file?path=%2Ftmp%2Fplot.png");
  assert.equal(fileUrl("/tmp/plot.png", null), "/file?path=%2Ftmp%2Fplot.png");
});

test("a host-prefixed sid routes through /remote/<host>/file with the bare sid", () => {
  assert.equal(fileUrl("/tmp/plot.png", "gpu1:" + UUID),
               "/remote/gpu1/file?path=%2Ftmp%2Fplot.png&sid=" + UUID);
});

test("a relative path rides through too — the REMOTE kernel resolves it against its session's cwd", () => {
  assert.equal(fileUrl("plots/out.png", "gpu1:" + UUID),
               "/remote/gpu1/file?path=plots%2Fout.png&sid=" + UUID);
});
