// TeX math for chat markdown: inline \( .. \) and $ .. $, display \[ .. \] and $$ .. $$
// (the user 2026-08-03). marked has no math syntax, so without this every formula an agent
// writes reaches the transcript as raw TeX source. KaTeX renders with output: "html" ONLY,
// no MathML twin, so the result passes md()'s DOMPurify html profile untouched and the
// sanitizer never widens for math. The KaTeX layout CSS ships via styles.css
// (@import "katex/dist/katex.min.css"; fonts emitted to dist/fonts/ by esbuild).
//
// The delimiter problem: `$` is everywhere in chat text that is NOT math (shell variables,
// prices), and a naive $..$ tokenizer strikes a formula through half a sentence the way the
// single-tilde del rule once did (render.ts). Code spans and fences are already safe: marked
// consumes them whole when the inline walker reaches the backtick, and a backtick never
// enters math content (rule below), so a candidate can never pair up across a code-span
// boundary either. The rules that disarm bare prose, for inline $ .. $ only:
//   - the opener $ must touch its content: "$x", "$5", never "$ x"
//   - content stays on one line and contains no $ and no backtick
//   - the closer $ must touch its content AND be followed by end-of-text, whitespace, or
//     closing punctuation. This is the rule that spares shell and price prose: "$HOME/$USER"
//     (closer followed by "U"), "$FOO,$BAR" (followed by "B"), "$5-$10" (followed by "1")
//     all stay literal, while "$x$-axis" and "**$O(n)$**" still render ("-", "*" are in
//     the set).
// \( \) / \[ \] / $$ $$ carry no real ambiguity and pass through with only a non-blank
// content check. Escaped \$ needs nothing: the walker meets the backslash first and marked's
// escape tokenizer consumes both characters before any math rule sees the $.
import katex from "katex";
import type { TokenizerAndRendererExtension, Tokens } from "marked";

type MathToken = Tokens.Generic & { text: string; display: boolean };

// Closing punctuation allowed right after the closing $ (plus whitespace / end-of-text).
// Includes markdown emphasis/strike markers so **$O(n)$** works, and the common CJK stops.
const AFTER_CLOSE = "[\\s.,;:!?)\\]}\"'*_~\\-、。，；：！？）】」]";

const INLINE_PAREN = /^\\\(([\s\S]+?)\\\)/;                 // \( .. \)   inline
const INLINE_BRACKET = /^\\\[([\s\S]+?)\\\]/;               // \[ .. \]   display
const INLINE_DOLLARS = /^\$\$([\s\S]+?)\$\$/;               // $$ .. $$   display
const INLINE_DOLLAR = new RegExp(
  "^\\$(?![\\s$])([^$\\n`]*?[^\\s$\\n`])\\$(?=" + AFTER_CLOSE + "|$)",
);

// Block-level display math: a $$ .. $$ or \[ .. \] paragraph of its own, so multi-line
// formulas never reach markdown's block rules (a "- " or "#" line inside a formula would
// otherwise be carved into a list or heading before the inline pass could see it).
const BLOCK_DOLLARS = /^ {0,3}\$\$([\s\S]+?)\$\$ *(?:\n+|$)/;
const BLOCK_BRACKET = /^ {0,3}\\\[([\s\S]+?)\\\] *(?:\n+|$)/;

function renderTex(tex: string, display: boolean): string {
  // throwOnError: false renders bad TeX as visibly-flagged source instead of throwing; the
  // catch is a belt for the residual throws (wrong option types, internal errors), falling
  // back to the escaped literal so a formula can never blank a message.
  try {
    return katex.renderToString(tex, { displayMode: display, throwOnError: false, output: "html" });
  } catch {
    const esc = tex.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    return display ? `<pre><code>${esc}</code></pre>` : `<code>${esc}</code>`;
  }
}

export const mathBlock: TokenizerAndRendererExtension = {
  name: "mathBlock",
  level: "block",
  start(src: string) {
    const m = src.match(/(?:^|\n) {0,3}(?:\$\$|\\\[)/);
    return m ? m.index : undefined;
  },
  tokenizer(src: string) {
    const m = BLOCK_DOLLARS.exec(src) || BLOCK_BRACKET.exec(src);
    if (!m || !m[1].trim()) return undefined;
    return { type: "mathBlock", raw: m[0], text: m[1].trim(), display: true } as MathToken;
  },
  renderer(token) {
    return renderTex((token as MathToken).text, true);
  },
};

export const mathInline: TokenizerAndRendererExtension = {
  name: "mathInline",
  level: "inline",
  start(src: string) {
    const m = src.match(/\$|\\\(|\\\[/);
    return m ? m.index : undefined;
  },
  tokenizer(src: string) {
    let m: RegExpExecArray | null; let display = false;
    if ((m = INLINE_PAREN.exec(src))) display = false;
    else if ((m = INLINE_BRACKET.exec(src)) || (m = INLINE_DOLLARS.exec(src))) display = true;
    else m = INLINE_DOLLAR.exec(src);
    if (!m || !m[1].trim()) return undefined;
    return { type: "mathInline", raw: m[0], text: m[1].trim(), display } as MathToken;
  },
  renderer(token) {
    const t = token as MathToken;
    return renderTex(t.text, t.display);
  },
};
