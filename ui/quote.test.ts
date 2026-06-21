import { test } from "node:test";
import assert from "node:assert";
import { quoteReply } from "./quote";

test("quoteReply: single line into an empty composer, caret at end", () => {
  const r = quoteReply("hello world", "");
  assert.equal(r.value, "> hello world\n\n");
  assert.equal(r.caret, r.value.length);
});

test("quoteReply: every line of a multi-line selection is blockquoted", () => {
  const r = quoteReply("line one\nline two", "");
  assert.equal(r.value, "> line one\n> line two\n\n");
});

test("quoteReply: a blank line inside the selection becomes a bare '>'", () => {
  const r = quoteReply("para one\n\npara two", "");
  assert.equal(r.value, "> para one\n>\n> para two\n\n");
});

test("quoteReply: surrounding blank space in the selection is trimmed", () => {
  const r = quoteReply("  \n  hi  \n  ", "");
  assert.equal(r.value, "> hi\n\n");
});

test("quoteReply: CRLF / CR are normalized to LF", () => {
  const r = quoteReply("a\r\nb\rc", "");
  assert.equal(r.value, "> a\n> b\n> c\n\n");
});

test("quoteReply: appends to an existing draft with one blank-line separator", () => {
  const r = quoteReply("quote", "my draft");
  assert.equal(r.value, "my draft\n\n> quote\n\n");
  assert.equal(r.caret, r.value.length);
});

test("quoteReply: always exactly one blank line between draft and quote", () => {
  assert.equal(quoteReply("q", "draft").value, "draft\n\n> q\n\n");      // no trailing newline
  assert.equal(quoteReply("q", "draft\n").value, "draft\n\n> q\n\n");    // one trailing newline
  assert.equal(quoteReply("q", "draft\n\n").value, "draft\n\n> q\n\n");  // already a blank line
});
