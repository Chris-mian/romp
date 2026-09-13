/** The writer CENSUS of a source (T386 stage 1, round seven): every call of the scroll-write family, read with the TypeScript
 *  compiler's own parser, so strings, template literals, regular expressions, comments and nesting are what the language says
 *  they are, never what a regular expression guessed.
 *
 *  The rule the census enforces (landing-settle.ts WRITER_CLASS and WRITER_WRAPPERS): at a call of the write helper or of a
 *  registered wrapper, the argument at the writer's position is a PLAIN STRING LITERAL, or it is a parameter of the enclosing
 *  function, which is then a wrapper and must be in the table at that parameter's position. Anything else at that position, a
 *  template literal, a concatenation, a module-level constant, a variable, a spread, is a FAILURE naming the call; a function
 *  that passes one of its own parameters through, whatever the parameter is called and however the function is written (async,
 *  nested, a method, an arrow), is a wrapper and must be registered; a registered name that passes nothing through is stale.
 *  The table's root (the write helper itself) is the one entry that forwards to nothing.
 *
 *  Node-only: the tests import it; the webview bundle never does. */
import * as ts from "typescript";

export type CensusFailure = { line: number; call: string; why: string };
export type WriterCensus = {
  /** every plain string literal at a writer position, sorted, unique */
  literals: string[];
  /** every function that passes one of its own parameters at a writer position, with that parameter's index */
  wrappers: Record<string, number>;
  /** every call and every wrapper the rule refuses, each naming its line */
  failures: CensusFailure[];
};

/** A writer name: lower-case words and digits, hyphen-joined (the ledger's vocabulary). */
export const WRITER_NAME = /^[a-z][a-z0-9-]*$/;

export function writerCensus(src: string, table: Readonly<Record<string, number>>, root = "writeScroll", file = "render.ts"): WriterCensus {
  const sf = ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const literals = new Set<string>();
  const wrappers: Record<string, number> = {};
  const wrapperLine: Record<string, number> = {};
  const failures: CensusFailure[] = [];
  const lineOf = (n: ts.Node): number => sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1;
  const shown = (n: ts.Node): string => n.getText(sf).replace(/\s+/g, " ").slice(0, 90);
  const fail = (n: ts.Node, call: string, why: string): void => { failures.push({ line: lineOf(n), call, why }); };
  /** The argument's kind by its node (SyntaxKind's numeric aliases print their first name: a template literal without a substitution
   *  would read FirstTemplateToken). */
  const kindName = (n: ts.Node): string => ts.isNoSubstitutionTemplateLiteral(n) ? "NoSubstitutionTemplateLiteral" : ts.isTemplateExpression(n) ? "TemplateExpression" : ts.SyntaxKind[n.kind];

  /** The function that OWNS a parameter name at a use site: the nearest enclosing function whose parameter list names it (an
   *  inner function's parameter of the same name shadows an outer one, as in the language). */
  const ownerOf = (from: ts.Node, name: string): { fn: ts.SignatureDeclaration; index: number } | null => {
    for (let n: ts.Node | undefined = from.parent; n; n = n.parent) {
      if (ts.isFunctionLike(n)) {
        const index = n.parameters.findIndex((p) => ts.isIdentifier(p.name) && p.name.text === name);
        if (index >= 0) return { fn: n, index };
      }
    }
    return null;
  };
  /** A function's name however it is written: a declaration's or method's own, the variable or property it is assigned to. */
  const nameOf = (fn: ts.SignatureDeclaration): string | null => {
    if ((ts.isFunctionDeclaration(fn) || ts.isMethodDeclaration(fn) || ts.isFunctionExpression(fn)) && fn.name) return fn.name.getText(sf);
    const p = fn.parent;
    if (p && ts.isVariableDeclaration(p) && ts.isIdentifier(p.name)) return p.name.text;
    if (p && (ts.isPropertyAssignment(p) || ts.isPropertyDeclaration(p))) return p.name.getText(sf);
    return null;
  };

  const visit = (n: ts.Node): void => {
    if (ts.isCallExpression(n) && ts.isIdentifier(n.expression) && Object.prototype.hasOwnProperty.call(table, n.expression.text)) {
      const callee = n.expression.text;
      const pos = table[callee];
      const arg = n.arguments[pos];
      const call = shown(n);
      if (!arg) fail(n, call, callee + " takes its writer at position " + pos + " and this call passes nothing there");
      else if (ts.isStringLiteral(arg)) {
        if (WRITER_NAME.test(arg.text)) literals.add(arg.text);
        else fail(n, call, JSON.stringify(arg.text) + " is not a writer name (lower-case words and digits, hyphen-joined)");
      } else if (ts.isIdentifier(arg)) {
        const owner = ownerOf(n, arg.text);
        if (!owner) fail(n, call, "the writer is the variable " + arg.text + ": not a plain string literal, and not a parameter of any enclosing function");
        else {
          const wname = nameOf(owner.fn);
          if (!wname) fail(n, call, "an anonymous function passes its parameter " + arg.text + " as the writer: name it and register it in WRITER_WRAPPERS");
          else {
            if (wname in wrappers && wrappers[wname] !== owner.index) fail(owner.fn, wname, "passes its writer from two positions (" + wrappers[wname] + " and " + owner.index + ")");
            wrappers[wname] = owner.index;
            wrapperLine[wname] = lineOf(owner.fn);
          }
        }
      } else fail(n, call, "the writer is " + kindName(arg) + ", not a plain string literal");
    }
    ts.forEachChild(n, visit);
  };
  visit(sf);

  for (const w of Object.keys(wrappers)) {
    if (!Object.prototype.hasOwnProperty.call(table, w)) failures.push({ line: wrapperLine[w], call: w, why: "passes its parameter " + wrappers[w] + " to the family and is not in WRITER_WRAPPERS" });
    else if (table[w] !== wrappers[w]) failures.push({ line: wrapperLine[w], call: w, why: "is registered at position " + table[w] + " but passes its parameter " + wrappers[w] });
  }
  for (const t of Object.keys(table)) {
    if (t === root || Object.prototype.hasOwnProperty.call(wrappers, t)) continue;
    failures.push({ line: 0, call: t, why: "is in WRITER_WRAPPERS but passes no parameter of its own to the family in this source" });
  }
  // the root: a function of that name, with a parameter at the table's position
  let rootSeen = false;
  const findRoot = (n: ts.Node): void => {
    if (ts.isFunctionDeclaration(n) && n.name && n.name.text === root) { rootSeen = true; if (n.parameters.length <= table[root]) failures.push({ line: lineOf(n), call: root, why: "the root has no parameter at position " + table[root] }); }
    else ts.forEachChild(n, findRoot);
  };
  findRoot(sf);
  if (!rootSeen) failures.push({ line: 0, call: root, why: "the root is not declared as a function in this source" });

  failures.sort((a, b) => a.line - b.line || a.call.localeCompare(b.call));
  return { literals: [...literals].sort(), wrappers, failures };
}
