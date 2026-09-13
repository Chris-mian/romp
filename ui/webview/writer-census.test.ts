// The writer census's own shapes (T386 stage 1, round seven, mediums 1 and 2): every way a writer argument or a wrapper can be written
// that a regular-expression extractor read wrong or skipped in silence, each executed through the census on the compiler's parser.
// The census of render.ts itself is pinned in landing-settle.test.ts; this file pins the CENSUS.
import test from "node:test";
import assert from "node:assert/strict";
import { writerCensus } from "./writer-census";

// a small family for the shapes: the root, a wrapper at position 2, a wrapper at position 0
const TABLE = { writeScroll: 2, scrollContentBy: 2, land: 0 } as const;
const ROOT =
  "function writeScroll(el: HTMLElement, top: number, writer: string, stick?: boolean): void { el.scrollTop = top; }\n" +
  "function scrollContentBy(el: HTMLElement, dy: number, writer: string): void { writeScroll(el, el.scrollTop + dy, writer); }\n" +
  "function land(writer: string, el: HTMLElement): void { writeScroll(el, 0, writer); }\n";
const census = (body: string, table: Readonly<Record<string, number>> = TABLE) => writerCensus(ROOT + body, table);
const whys = (c: ReturnType<typeof writerCensus>) => c.failures.map((f) => f.line + " " + f.call + ": " + f.why);

test("round six's shapes still read: a stick flag as a variable, a name with a digit, a wrapper's literal, and the family's own wrappers", () => {
  const c = census('writeScroll(el, top, "plain-one"); const stick = v.stick; writeScroll(el, top, "stick-var", stick); scrollContentBy(el, 12, "step-2"); land("land-on", el);');
  assert.deepEqual(c.failures, [], whys(c).join("\n"));
  assert.deepEqual(c.literals, ["land-on", "plain-one", "step-2", "stick-var"]);
  assert.deepEqual(c.wrappers, { scrollContentBy: 2, land: 0 }, "the family's wrappers, found by their bodies, at their positions");
});

// MEDIUM 1: a writer that is not a plain string literal is a FAILURE naming the call, never a silent skip
for (const [shape, body, why] of [
  ["a template literal", "writeScroll(el, top, `land-${where}`);", /TemplateExpression, not a plain string literal/],
  ["a template literal without a substitution", "writeScroll(el, top, `land-on`);", /NoSubstitutionTemplateLiteral, not a plain string literal/],
  ["a concatenation", 'writeScroll(el, top, "land-" + kind);', /BinaryExpression, not a plain string literal/],
  ["a module-level const", 'const WRITER = "land-on";\nfunction go(el: HTMLElement): void { writeScroll(el, 0, WRITER); }', /the variable WRITER: not a plain string literal, and not a parameter of any enclosing function/],
  ["a local variable", 'function go(el: HTMLElement): void { let w = "land-on"; writeScroll(el, 0, w); }', /the variable w: not a plain string literal/],
  ["a property", "writeScroll(el, top, names.landOn);", /PropertyAccessExpression, not a plain string literal/],
  ["a call", "writeScroll(el, top, writerFor(x));", /CallExpression, not a plain string literal/],
  ["a conditional", 'writeScroll(el, top, big ? "land-far" : "land-near");', /ConditionalExpression, not a plain string literal/],
  ["a spread that leaves the position empty", "writeScroll(...args);", /passes nothing there/],
  ["a string that is not a writer name", 'writeScroll(el, top, "Land On");', /is not a writer name/],
] as const) {
  test("medium 1: " + shape + " at the writer's position fails the census naming the call", () => {
    const c = census(body);
    assert.equal(c.failures.length, 1, "one failure, the call: " + whys(c).join(" | "));
    assert.match(c.failures[0].why, why);
    assert.match(c.failures[0].call, /^writeScroll\(/, "the failure names the call: " + c.failures[0].call);
    assert.ok(c.failures[0].line > 3, "the failure names the line, past the family's own three: " + c.failures[0].line);
    assert.deepEqual(c.literals, [], "nothing was counted from a non-literal");
  });
}

// what the old extractor read wrong or skipped, now read as the language reads it
test("a single-quoted literal is a plain string literal and is counted", () => {
  const c = census("writeScroll(el, top, 'quoted-one');");
  assert.deepEqual(c.failures, [], whys(c).join("\n"));
  assert.deepEqual(c.literals, ["quoted-one"]);
});
test("a regular expression with an unbalanced parenthesis in another argument does not derail the call", () => {
  const c = census('writeScroll(el, /\\(/.test(s) ? 1 : 2, "after-regex");');
  assert.deepEqual(c.failures, [], whys(c).join("\n"));
  assert.deepEqual(c.literals, ["after-regex"]);
});
test("a block comment with an unbalanced brace inside the call does not derail it", () => {
  const c = census('writeScroll(el, top /* { */, "after-comment");');
  assert.deepEqual(c.failures, [], whys(c).join("\n"));
  assert.deepEqual(c.literals, ["after-comment"]);
});
test("a call inside a comment or a string is text, not a call", () => {
  const c = census('// writeScroll(el, top, "in-a-comment")\n/* writeScroll(el, top, "in-a-block") */\nconst s = \'writeScroll(el, top, "in-a-string")\';');
  assert.deepEqual(c.failures, [], whys(c).join("\n"));
  assert.deepEqual(c.literals, []);
});

// MEDIUM 2: a wrapper is found by its BODY, whatever it is called and however it is written, and must be in the table at its position
for (const [shape, body, name, index, through] of [
  ["an async function", "async function wAsync(el: HTMLElement, writer: string): Promise<void> { writeScroll(el, 0, writer); }", "wAsync", 1, "writeScroll"],
  ["a nested function", 'function outer(): void { function wNested(x: string): void { writeScroll(el, 0, x); } wNested("land-on"); }', "wNested", 0, "writeScroll"],
  ["a renamed parameter", "function wRenamed(el: HTMLElement, who: string): void { scrollContentBy(el, 1, who); }", "wRenamed", 1, "scrollContentBy"],
  ["a method", "class K { go(el: HTMLElement, w: string): void { writeScroll(el, 0, w); } }", "go", 1, "writeScroll"],
  ["an arrow assigned to a const", "const wArrow = (w: string, el: HTMLElement): void => land(w, el);", "wArrow", 0, "land"],
  ["a function expression assigned to a property", "const api = { move: function (el: HTMLElement, dy: number, w: string) { writeScroll(el, dy, w); } };", "move", 2, "writeScroll"],
  ["an arrow inside a nested block", "function a(): void { if (x) { const wDeep = (w: string) => { writeScroll(el, 0, w); }; wDeep('land-on'); } }", "wDeep", 0, "writeScroll"],
] as const) {
  test("medium 2: " + shape + " passing its own parameter is a wrapper the table must name at its position", () => {
    const c = census(body);
    assert.equal(c.wrappers[name], index, "found by its body, at the parameter's index: " + JSON.stringify(c.wrappers));
    const f = c.failures.filter((x) => x.call === name);
    assert.equal(f.length, 1, "one failure, the unregistered wrapper: " + whys(c).join(" | "));
    assert.match(f[0].why, /is not in WRITER_WRAPPERS/);
    assert.ok(f[0].line > 3, "the failure names the wrapper's line: " + f[0].line);
    // the literal a caller hands the unregistered wrapper is NOT counted until the table names it
    assert.ok(!c.literals.includes("land-on"), "nothing counted through an unregistered wrapper: " + c.literals.join(","));
    // registered at its position, the same source is clean and the wrapper's callers are read
    const ok = census(body + '\n' + name + (index === 0 ? '("via-wrapper", el)' : index === 1 ? '(el, "via-wrapper")' : '(el, 1, "via-wrapper")') + ";", { ...TABLE, [name]: index });
    assert.deepEqual(ok.failures.filter((x) => x.call === name || /via-wrapper/.test(x.call)), [], whys(ok).join("\n"));
    assert.ok(ok.literals.includes("via-wrapper"), "a literal through the registered wrapper is counted: " + ok.literals.join(",") + " (through " + through + ")");
  });
}

test("medium 2: an anonymous function passing its parameter through fails naming the call", () => {
  const c = census("items.forEach((w: string) => writeScroll(el, 0, w));");
  assert.equal(c.failures.length, 1, whys(c).join(" | "));
  assert.match(c.failures[0].why, /an anonymous function passes its parameter w/);
});
test("medium 2: an inner parameter of the same name shadows the outer one; the inner function is the wrapper", () => {
  const c = census("function wOuter(writer: string): void { const inner = (writer: string) => writeScroll(el, 0, writer); inner(writer); }");
  assert.deepEqual(c.wrappers, { scrollContentBy: 2, land: 0, inner: 0 }, JSON.stringify(c.wrappers));
  assert.deepEqual(c.failures.map((f) => f.call), ["inner"], whys(c).join(" | "));
});
test("a registered wrapper at the wrong position fails", () => {
  const c = census("function wWrong(el: HTMLElement, writer: string): void { writeScroll(el, 0, writer); }", { ...TABLE, wWrong: 0 });
  assert.deepEqual(whys(c).filter((w) => /wWrong/.test(w)).length, 1, whys(c).join(" | "));
  assert.match(c.failures.find((f) => f.call === "wWrong")!.why, /registered at position 0 but passes its parameter 1/);
});
test("a stale table entry fails: a name that passes nothing through", () => {
  const c = census("", { ...TABLE, ghost: 1 });
  assert.match(c.failures.find((f) => f.call === "ghost")!.why, /passes no parameter of its own to the family/);
});
test("a wrapper passing its writer from two positions fails", () => {
  const c = census("function wTwo(a: string, b: string): void { writeScroll(el, 0, a); writeScroll(el, 1, b); }", { ...TABLE, wTwo: 0 });
  assert.ok(c.failures.some((f) => f.call === "wTwo" && /two positions/.test(f.why)), whys(c).join(" | "));
});
test("the root must be declared: a table whose root is missing fails", () => {
  const c = writerCensus('function other(el: HTMLElement, w: string): void { el.scrollTop = 0; }', { writeScroll: 2 });
  assert.match(c.failures.find((f) => f.call === "writeScroll")!.why, /not declared as a function/);
});
