// The glossary's client half, executed (T351 stage 2): the forms an entry links under, the matcher's rules (longest
// first, whole-word, case-insensitive, the skip list, the link modes), the term card's contract, over the same
// synthetic fixture the kernel's parser test reads; the wiring sparred.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { pluralForms, linkForms, skipForms, buildMatcher, scanTerms, noLinkZones, seenFromLinked, TERM_SKIP_SELECTOR, type GlossaryIndex, type GlossaryEntry } from "./glossary-links";

const FIX = JSON.parse(fs.readFileSync(path.resolve(process.cwd(), "..", "tests", "fixtures", "glossary_grammar.json"), "utf8"));
const IX: GlossaryIndex = { group: "notes-api", path: "~/.claude/glossaries/notes-api.md", skip: FIX.expect.skip, terms: FIX.expect.terms };
const GL = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "glossary-links.ts"), "utf8");
const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "kernel.py"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
const fn2 = (name: string) => { const i = RENDER.indexOf("function " + name + "("); const b = RENDER.slice(i); return b.slice(0, b.indexOf("\n}\n") + 3); };

test("plurals by the everyday rule; an entry's forms are the term, its aliases and their plurals, minus the skip list; off links nothing", () => {
  assert.deepEqual(pluralForms("tessel"), ["tessels"]); assert.deepEqual(pluralForms("quill"), ["quills"]); assert.deepEqual(pluralForms("bramblet"), ["bramblets"]);
  assert.deepEqual(pluralForms("tessel head"), ["tessel heads"]); assert.deepEqual(pluralForms("query"), ["queries"]); assert.deepEqual(pluralForms("day"), ["days"]);
  const skip = new Set(IX.skip);
  const tessel = IX.terms[0] as GlossaryEntry;
  assert.deepEqual(linkForms(tessel, skip).sort(), ["tessel", "tessel head", "tessel heads", "tesselled", "tesselleds", "tessels", "review tessel", "review tessels"].sort());
  assert.deepEqual(linkForms(IX.terms[2] as GlossaryEntry, skip), [], "link: off");
  assert.deepEqual(linkForms({ ...tessel, term: "green", also: ["CI"] }, skipForms(IX.skip)), [], "the skip list is by WORD: a listed word's plurals go too (the review's low)");
  assert.deepEqual(linkForms({ ...tessel, term: "", also: ["s", "ok"] }, skip).sort(), ["ok", "oks"], "empty and one-letter forms link nothing");
  assert.ok(skipForms(["head"]).has("heads") && skipForms([" Head "]).has("head"));
});

test("the matcher: longest form first, whole word, case-insensitive, Unicode-bounded; scanTerms honours all / first / off", () => {
  const m = buildMatcher(IX)!;
  assert.ok(m);
  const text = "I tesselled the fixes and pushed the tessel head; the Tessel is green, the quill and the quill again, spars sparred, untesselled, tessel-ish, T351.";
  const seen = new Set<GlossaryEntry>();
  const spans = scanTerms(text, m, seen).map((s) => [text.slice(s.start, s.end), s.entry.term]);
  assert.deepEqual(spans, [["tesselled", "tessel"], ["tessel head", "tessel head"], ["Tessel", "tessel"], ["quill", "quill"]],
    "tessel head is one term (longest first), Tessel matches case-insensitively, quill once (first), spars never (off), green never (skip), untesselled and tessel-ish are not whole words (a letter or a hyphen against the form)");
  assert.deepEqual(scanTerms("the quill again", m, seen), [], "first: the message's set carries across its text nodes");
  assert.deepEqual(scanTerms("the quill again", m, new Set()).length, 1, "a new message starts over");
  assert.deepEqual(scanTerms("tessel\u00e9 tessels", m, new Set()).map((s) => text && s.start), [8], "a letter after the form is not a boundary; the plural is a form");
  assert.equal(buildMatcher({ ...IX, terms: [IX.terms[2]] }), null, "an index that links nothing has no matcher");
  assert.equal(buildMatcher({ ...IX, terms: [{ ...IX.terms[0], term: "", also: [] }] }), null, "an empty-named entry links nothing (not even the letter s)");
  // no link inside a path-shaped or host-shaped token: a path the kernel could not verify, a bare host
  const zones = (s: string) => noLinkZones(s).map(([a, b]) => s.slice(a, b));
  assert.deepEqual(zones("see docs/widget/tessel.md and example.com/tessel/y, then ~/.claude/tessel.md, http://x.test/tessel and a tessel"),
                   ["docs/widget/tessel.md", "example.com/tessel/y", "~/.claude/tessel.md", "http://x.test/tessel"]);
  assert.deepEqual(zones("a bare host example.com, a file tessel.md, a parenthesised (docs/x/tessel.md) and 'lib/tessel'; not e.g. or v1.2 or 3.14."),
                   ["example.com", "tessel.md", "docs/x/tessel.md", "lib/tessel"], "one dot makes a host or a file name; a bracket or quote may precede the token");
  const seeded = seenFromLinked(["quill", "nonesuch"], m);
  assert.deepEqual(Array.from(seeded).map((e) => e.slug), ["quill"], "spans already linked under the root seed the seen set…");
  assert.deepEqual(scanTerms("the quill again", m, seeded), [], "…so a first-mode term linked in a nested body is not linked again around it");
  const t2 = "the tessel in docs/widget/tessel.md and on api.example.org/tessel stays plain; this tessel links";
  assert.deepEqual(scanTerms(t2, m, new Set()).map((s) => s.start), [4, t2.lastIndexOf("tessel")], "only the two prose occurrences");
});

test("a linked term is a path link to the glossary's section and nothing more: no card of its own, the ordinary link dress (T375)", () => {
  assert.ok(!GL.includes("termContent"), "the term card builder is gone from the module");
  assert.ok(!RENDER.includes("if (a.dataset.term)"), "showFilePreview has no term branch: the term rides the file-link road");
  assert.ok(!RENDER.includes("termContent("), "…and nothing fills a card from the index");
  assert.match(RENDER, /s\.dataset\.path = m\.index\.path; s\.dataset\.frag = e\.slug;\s*\n\s*s\.dataset\.preview = "markdown";/, "the span carries the glossary path, the slug as the section and the kind the kernel judged");
  assert.ok(!/s\.title = e\.plainWords/.test(RENDER), "no native title beside the hover card: one mechanism");
  assert.match(TERM_SKIP_SELECTOR, /code, pre, a, \.file-uri-link, h1, h2, h3, h4, h5, h6, \.katex, svg, \.term-link, \.cmt-pop, \.file-preview-pop/);
  // the dress: a link like any link (the user 2026-09-12): the link colour token, a solid underline, the pointer
  assert.match(CSS, /\.term-link \{ color: var\(--link\); text-decoration: underline solid; text-underline-offset: 2px; cursor: pointer; \}/);
  assert.ok(!/\.term-link[^\n]*dotted/.test(CSS) && !/\.term-link[^\n]*cursor: help/.test(CSS), "no dotted underline, no help cursor");
  assert.ok(!/\.term-link\.term-retired \{ opacity/.test(CSS), "no distinct dress for a retired term either: only the link marks a term");
  assert.ok(!CSS.includes(".fp-term") && !CSS.includes(".fp-open"), "the card-only styling and the open control's rules are gone");
});

test("the wiring: the frame per session, the matcher per index, links at the two chat grammars and the mail body, the card on the popover, the click to the viewer", () => {
  assert.match(RENDER, /else if \(m\.type === "glossary" && typeof m\.id === "string"\) \{[\s\S]{0,300}?glossaries\.set\(m\.id, m as GlossaryIndex\);\s*\n\s*relinkTerms\(m\.id\);/);
  assert.equal((RENDER.match(/\blinkTerms\((full|bubble|body)\)/g) || []).length, 6, "the nudge, continue and tagged-template bubbles' full text, the user bubble, the assistant body, the mail body (the review's low: the two bubbles never linked)");
  assert.match(RENDER, /linkifyFileUris\(body, undefined, ev\.spacePaths, ev\.pathLinks, ev\.pathPins, ev\.pathPreview, ev\.pathPreviewWhy\);[^\n]*\n\s*linkTerms\(body\);/, "after the path links, so a path token is never split by a term");
  assert.match(RENDER, /s\.dataset\.path = m\.index\.path; s\.dataset\.frag = e\.slug;[\s\S]{0,200}?armFilePreview\(s\);/, "a term span IS a path link: the same hover road (the section at the slug through the slice route)");
  assert.match(RENDER, /closest\?\.\("span\.term-link"\)[\s\S]{0,300}?openPath\(s\.dataset\.path \|\| "", s\.dataset\.gsid \|\| activeId, e, s\.dataset\.frag \|\| null\);/, "a click opens the glossary at the heading");
  assert.match(RENDER, /function relinkTerms\(sid: string\): void \{[\s\S]{0,700}?querySelectorAll\("span\.term-link"\)/, "a new index unwraps and re-links the view");
  assert.match(RENDER, /querySelectorAll\("\[data-term-root\]"\)\)\) linkTerms\(root as HTMLElement, sid\);/, "…exactly the marked roots, never every .md (the review's medium)");
  assert.match(fn2("linkTerms"), /if \(root\.parentElement\?\.closest\("\[data-term-root\]"\)\) return 0;\s*\n\s*root\.dataset\.termRoot = "1";/, "a nested root is its ancestor's to scan, one seen set per message");
  assert.doesNotMatch(RENDER, /querySelectorAll\("\.md"\)\)\) linkTerms/, "no relink over every .md");
  assert.equal((RENDER.match(/const full = el\("div", "nudge-full md"\);\s*\n\s*full\.innerHTML = md\(ev\.md\);\s*\n\s*linkTerms\(full\);/g) || []).length, 2,
               "the Continue-send and tagged-template bubbles link at render too (the review's low: built as nudge-full md with no linkTerms, they never linked)");
  assert.match(CSS, /\.term-link \{ color: var\(--link\); text-decoration: underline solid; text-underline-offset: 2px; cursor: pointer; \}/, "the ordinary link dress (T375; the dress test above says the rest)");
  // the kernel: the frame on the pusher's cycle beside the comments frame, on its own slot; the route; the byte cap and its /perf note
  assert.match(KERNEL, /gfr = _glossary_frame\(s\["sid"\]\)[\s\S]{0,400}?_send_client\(c, \("glossary", s\["sid"\]\), gfr\)/);
  assert.match(KERNEL, /if p\.startswith\("\/glossary\/"\):[\s\S]{0,300}?_glossary_lookup\(\(q\.get\("sid"\) or \[None\]\)\[0\], unquote\(p\[len\("\/glossary\/"\):\]\)\)/, "the route sits in the GET router beside the file route");
  assert.match(KERNEL, /_GLOSSARY_INDEX_MAX_BYTES = 256 \* 1024/); assert.match(KERNEL, /"glossary": glossary_stats,/);
  assert.match(KERNEL, /a bullet\s*\n\s*describing a PATTERN \(a T followed by a number, say\) is just words the whole-word matcher will never meet/, "the skip list is words, no special case for a pattern (said in the parser's docstring)");
});
