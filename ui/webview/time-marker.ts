// Pure label logic for the chat rail's HH:MM time-markers, split out of render.ts
// so it can be unit-tested without a DOM. renderEvent() wraps the returned text in
// a `.time-marker` div (with the `day` class when `day` is true).

export const WEEKDAY = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
export const MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export interface MarkerLabel {
  text: string; // "" → suppressed (same minute as the previous timed turn)
  day: boolean; // true → first turn of a past day; emphasise + show the date
  hm: string;   // the bare "HH:MM", ALWAYS — what a suppressed turn shows if the
                // spacing pass later lights it up (see chooseStamps).
  date: string; // the date word ("Yesterday" / "Mon" / "Jun 3") on a day marker, else "".
                // Named so the renderer can stack it on its OWN line above hm — a combined
                // "Yesterday · 21:24" overruns the narrow rail gutter and hits the dot.
}

// HH:MM for a turn, given the previous TIMED turn's epoch (or null) and "now".
// Rules, in order:
//   1. First turn of a past (non-today) day → "Yesterday · 11:03" / "Mon · …" / "Jun 3 · …", emphasised.
//   2. Same minute AND same day as the previous timed turn → suppressed (""), so a run of
//      same-minute events (11:03, 11:03, 11:03, 11:04) shows the stamp only when it changes.
//   3. Otherwise → "HH:MM".
// `hm` is the bare "HH:MM" regardless of the rule, so a suppressed turn still carries the
// time the spacing pass can reveal when too much vertical space has gone unstamped.
export function markerLabel(epoch: number, prevEpoch: number | null, nowMs: number): MarkerLabel {
  const d = new Date(epoch * 1000);
  const dayKey = (x: Date) => `${x.getFullYear()}/${x.getMonth()}/${x.getDate()}`;
  const time = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  const now = new Date(nowMs);
  const prev = prevEpoch == null ? null : new Date(prevEpoch * 1000);
  const dayChanged = prev == null || dayKey(d) !== dayKey(prev);
  const isToday = dayKey(d) === dayKey(now);
  if (dayChanged && !isToday) {
    const sod = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
    const days = Math.round((sod(now) - sod(d)) / 86400000);
    const date = days === 1 ? "Yesterday" : days < 7 ? WEEKDAY[d.getDay()] : `${MONTH[d.getMonth()]} ${d.getDate()}`;
    return { text: `${date} · ${time}`, day: true, hm: time, date };
  }
  const sameMinute = prev != null
    && dayKey(d) === dayKey(prev)
    && d.getHours() === prev.getHours()
    && d.getMinutes() === prev.getMinutes();
  if (sameMinute) return { text: "", day: false, hm: time, date: "" };
  return { text: time, day: false, hm: time, date: "" };
}

// Minute-change stamps alone can be too sparse: dozens of turns can land in one minute,
// leaving a long unstamped scroll. After layout we walk the timed turns top→bottom and
// reveal a suppressed stamp whenever more than `maxRows` one-line rows of vertical space
// have passed since the last visible stamp — so the rail never goes more than ~maxRows
// lines without telling you the time.
//
//   ys[i]   — vertical position (px) of turn i's dot, increasing down the rail.
//   hard[i] — true if turn i already shows a stamp from markerLabel (minute/day change).
//   oneRow  — px height of a single one-line turn (the rail's "one row" unit).
//   maxRows — reveal once the gap since the last stamp reaches this many rows (default 6).
// Returns a boolean per turn: should it show a stamp (hard stamps stay true).
export function chooseStamps(ys: number[], hard: boolean[], oneRow: number, maxRows = 6): boolean[] {
  const maxGap = maxRows * oneRow;
  const show = hard.slice();
  let lastY: number | null = null;
  for (let i = 0; i < ys.length; i++) {
    if (hard[i]) { lastY = ys[i]; continue; }
    if (lastY == null || ys[i] - lastY >= maxGap) { show[i] = true; lastY = ys[i]; }
  }
  return show;
}
