import { test } from "node:test";
import assert from "node:assert";
import { numberDiff } from "./diff-lines";

test("removed lines count up the OLD column, added lines up the NEW column, both from 1", () => {
  const rows = numberDiff("- old A\n- old B\n+ new A\n+ new B\n+ new C");
  assert.deepEqual(
    rows.map((r) => [r.sign, r.oldNo, r.newNo, r.text]),
    [
      ["-", 1, null, "old A"],
      ["-", 2, null, "old B"],
      ["+", null, 1, "new A"],
      ["+", null, 2, "new B"],
      ["+", null, 3, "new C"],
    ],
  );
});

test("the leading '+ ' / '- ' marker is stripped from the row text", () => {
  const [row] = numberDiff("+   indented new line");
  assert.equal(row.text, "  indented new line");   // only the 2-char marker is removed; inner indent kept
  assert.equal(row.sign, "+");
});

test("a single trailing newline does not produce a blank numbered row", () => {
  assert.equal(numberDiff("+ x\n").length, 1);
  assert.equal(numberDiff("- a\n+ b\n").length, 2);
});

test("an empty diff yields no rows", () => {
  assert.deepEqual(numberDiff(""), []);
});
