// Fuzzy subsequence matching for the command palette (Obsidian-style): every query character
// must appear in the text in order; the score rewards word starts, consecutive runs and early
// matches. Pure and DOM-free — the palette renders the returned ranges as highlights.

export type FuzzyRange = [number, number];   // [start, end) into the original text
export type FuzzyHit = { score: number; ranges: FuzzyRange[] };

// Greedy left-to-right walk, not optimal alignment: predictable, fast, and plenty for short
// command titles and session names. Spaces in the query order words but need no match of
// their own, so "open set" hits "Open settings" whether or not the greedy walk eats the space.
export function fuzzyMatch(query: string, text: string): FuzzyHit | null {
  const q = query.toLowerCase();
  const t = text.toLowerCase();
  if (!q.trim()) return { score: 0, ranges: [] };   // empty query matches everything, scoreless
  const idx: number[] = [];
  let ti = 0;
  for (let qi = 0; qi < q.length; qi++) {
    const c = q[qi];
    if (c === " ") continue;
    ti = t.indexOf(c, ti);
    if (ti < 0) return null;
    idx.push(ti);
    ti++;
  }
  let score = 0;
  for (let i = 0; i < idx.length; i++) {
    const p = idx[i];
    if (p === 0 || !/[a-z0-9]/.test(t[p - 1])) score += 3;   // start of the text or of a word
    if (i > 0 && idx[i - 1] === p - 1) score += 2;           // consecutive run
    score -= p * 0.01;                                       // earlier is a little better
  }
  const ranges: FuzzyRange[] = [];
  for (const p of idx) {
    const last = ranges[ranges.length - 1];
    if (last && last[1] === p) last[1] = p + 1;
    else ranges.push([p, p + 1]);
  }
  return { score, ranges };
}
