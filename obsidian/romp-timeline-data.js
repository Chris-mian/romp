'use strict';

// romp-timeline-data — builds the timeline payload for the Obsidian/VS Code Timeline tab.
//
// It no longer parses transcripts or binds summaries itself. The SINGLE host-side producer
// `romp-events --emit` owns ALL of that: it resolves sessions (live + ended, forks merged),
// extracts each session's work-period EVENTS, and binds each event's request/reply Haiku phrase
// by stable id. This builder just (a) runs that once, (b) reads tmux for live lane metadata
// (state/context/colour), and (c) keeps the inter-session MESSAGE side (postal log + maildir +
// positioning). That deletes the three-way duplicated parser/binder — boundary logic lives in
// exactly one place, and a summary can never bind to the wrong event (id-equality, no time window).
//
// Payload shape (unchanged): { now, sessions:[{name,color,state,live,…}], turns:{name:[turn]},
// messages:[…] }, where turn = { start, end, prompt, src, mids, pending, summary, reply }.

const HORIZON = 48 * 3600;   // how far back the awaiting-stripe log is read (matches slider max)
// Max wall-clock age for a message to still be "in flight" (riding the live `now` edge). A genuinely
// pending message is worked within minutes; one older than this isn't in flight, it's stale — most
// often because the machine SLEPT (lid closed) between send and now. Without this cap, on WAKE the
// `now` jumps forward and any not-yet-processed message snaps its connector to the new now, drawing a
// phantom "just landed" line from a now-idle sender (the recipient's @claude-state is also a stale
// 'working' across sleep, so the in-flight test passes). Capping age pins such a message at its real
// time instead — the sleep/wake analogue of the dead-gap bar clip.
const MSG_INFLIGHT_MAX = 1800;   // 30 min
// "Active" = working OR awaiting-your-input. Both sort to the top and keep their
// activity bar running to now; only idle/closed sessions sink.
const ACTIVE = (st) => st === 'working' || st === 'permission' || st === 'awaiting' || st === 'compacting';
// Tolerance (s) for "is the last recorded turn the CURRENT active run?": the in-progress turn's last
// assistant line lands at/after the active-run start, but a tiny idle blip or clock skew between the
// transcript and the state log shouldn't force a split. Gaps below this fold into the live turn.
const ACTIVE_LAG = 10;

function _node() {
  // All of these are esbuild "externals" — present in desktop Obsidian, absent on
  // mobile. Callers treat a throw / empty result as "timeline unavailable here".
  return {
    fs: require('fs'),
    path: require('path'),
    childProcess: require('child_process'),
  };
}
function homedir() { return process.env.HOME || process.env.USERPROFILE || ''; }

const TMUX_CANDIDATES = ['/opt/homebrew/bin/tmux', '/usr/local/bin/tmux', '/usr/bin/tmux', '/bin/tmux'];
let _tmuxPath;
function resolveTmux(fs) {
  if (_tmuxPath !== undefined) return _tmuxPath;
  _tmuxPath = 'tmux';
  try { for (const p of TMUX_CANDIDATES) if (fs.existsSync(p)) { _tmuxPath = p; break; } } catch (e) {}
  return _tmuxPath;
}

// romp-events is a stdlib-only python3 script at a stable path in the dotfiles repo. We resolve
// the ABSOLUTE path (the GUI PATH lacks the user's shell PATH) + python3 explicitly, with a
// PATH fallback. Cached after first resolve.
const PY_CANDIDATES = ['/opt/homebrew/bin/python3', '/usr/local/bin/python3', '/usr/bin/python3', '/bin/python3'];
let _pyPath;
function resolvePython(fs) {
  if (_pyPath !== undefined) return _pyPath;
  _pyPath = 'python3';
  try { for (const p of PY_CANDIDATES) if (fs.existsSync(p)) { _pyPath = p; break; } } catch (e) {}
  return _pyPath;
}
let _cePath;
function resolveRompEvents(node) {
  if (_cePath !== undefined) return _cePath;
  _cePath = 'romp-events';
  try {
    const cands = [
      process.env.ROMP_DIR && node.path.join(process.env.ROMP_DIR, 'bin', 'romp-events'),
      node.path.join(__dirname, '..', 'bin', 'romp-events'),
      node.path.join(homedir(), 'GitRepos', 'romp', 'bin', 'romp-events'),
    ].filter(Boolean);
    for (const cand of cands) if (node.fs.existsSync(cand)) { _cePath = cand; break; }
  } catch (e) {}
  return _cePath;
}

const TMUX_FORMAT =
  '#{@romp}|#{session_name}|#{@romp-session-id}|#{@claude-state}|#{@claude-state-since}|#{@identity-bg}|#{@claude-summary}|#{@claude-dir}|#{@claude-context}|#{@claude-model}|#{@claude-effort}';

function stateDir(node) {
  const base = process.env.XDG_STATE_HOME || node.path.join(homedir(), '.local', 'state');
  return node.path.join(base, 'romp');
}

// The romp-chat-view extension publishes its currently-active tab to <state>/romp/chat-active as
// JSON {tid, name} (tid = the active transcript id, name = its session label). Absent/empty = nothing
// active. The timeline reads it to outline whichever lane is currently open in the chat.
function readActiveChat(node) {
  try {
    const raw = node.fs.readFileSync(node.path.join(stateDir(node), 'chat-active'), 'utf8').trim();
    if (!raw) return null;
    const o = JSON.parse(raw);
    return { tid: o.tid || null, name: o.name || null };
  } catch (e) { return null; }
}

// Feed→timeline focus request: the romp feed (update_feed) writes {id,sid,t,nonce} here on a card
// click; the view scrolls/pulses to that event whenever the nonce CHANGES. id == the feed itemId ==
// romp-events e.id; sid+t locate the lane + time. null when absent/garbage/no nonce.
function readFocus(node) {
  try {
    const raw = node.fs.readFileSync(node.path.join(stateDir(node), 'timeline-focus.json'), 'utf8').trim();
    if (!raw) return null;
    const o = JSON.parse(raw);
    if (o == null || o.nonce == null) return null;
    // Optional request-DAG: the feed writes {ask, events:[romp-events ids], msgs:[postal ids]} to
    // outline an ask's full journey (typed turn → reply events → handoff connectors) in yellow.
    // Additive — pass it through untouched when well-formed, else null (no DAG overlay).
    let dag = null;
    if (o.dag && (Array.isArray(o.dag.events) || Array.isArray(o.dag.msgs))) {
      dag = { ask: o.dag.ask || null,
              events: Array.isArray(o.dag.events) ? o.dag.events : [],
              msgs: Array.isArray(o.dag.msgs) ? o.dag.msgs : [] };
    }
    // Explicit click-intent hint: 'work' = flash the BAR + open workUuid (even on a typed turn whose
    // reply was filed under the ask); 'prompt' = the start dot. Absent → view falls back to kind-inference.
    const anchor = (o.anchor === 'work' || o.anchor === 'prompt') ? o.anchor : null;
    // locate=false → a PAINT-only signal (feed-card hover preview, single-click, double-click toggle-OFF
    // clear): update the DAG overlay but DON'T jump (no pan/pulse/open). Absent → true (normal locate).
    const locate = o.locate === false ? false : true;
    // jump=true → an explicit "pan the timeline to this" intent (the feed's DOUBLE-CLICK), honored even on
    // a paint (locate:false) focus so a double-click pans WITHOUT a chat-open (the chat jump is first-party
    // in romp-chat-view). Hover/single-click omit it → no pan. (the user's rule: only double-click jumps.)
    const jump = o.jump === true ? true : undefined;
    return { id: o.id || null, sid: o.sid || null, t: (typeof o.t === 'number' ? o.t : null), nonce: o.nonce, dag, anchor, locate, jump };
  } catch (e) { return null; }
}

// Feed→timeline HOVER highlight (separate transient channel from focus): vs_chat writes
// timeline-hover.json = {id, sid, nonce} on modal line-hover (id = romp-events event id == turn.id;
// id null/absent = un-hover clear). The view draws a LIGHT glow on the matching event — no pan/pulse/
// open, distinct from timeline-focus.json's click behavior. null when absent/garbage/cleared.
function readHover(node) {
  try {
    const raw = node.fs.readFileSync(node.path.join(stateDir(node), 'timeline-hover.json'), 'utf8').trim();
    if (!raw) return null;
    const o = JSON.parse(raw);
    if (o == null) return null;
    // `ids` = the UNION of every event + delegation-message under the hovered line (a parent line covers
    // its whole subtree); `id` is kept as the first entry for back-compat. Each id matches EITHER a
    // romp-events event id (turn → bar/dot) OR a postal message id (connector/arrival dot). ids:null/
    // absent AND no id = cleared (nothing hovered).
    const arr = Array.isArray(o.ids) ? o.ids.filter((x) => x) : null;
    const ids = (arr && arr.length) ? arr : (o.id ? [o.id] : []);
    if (!ids.length) return null;
    return { id: ids[0], ids: ids, sid: o.sid || null, nonce: (o.nonce != null ? o.nonce : null) };
  } catch (e) { return null; }
}

// Account-wide Claude usage — the /usage rate-limit bars (5-hour + weekly), published by statusline.sh
// into a shared usage.json snapshot (rate_limits only reaches the statusLine for Pro/Max, after the
// first response; latest writer wins). null when nothing has reported yet / not on a plan.
function readUsage(node) {
  try {
    const o = JSON.parse(node.fs.readFileSync(node.path.join(stateDir(node), 'usage.json'), 'utf8'));
    const seg = (s) => (s && typeof s.pct === 'number')
      ? { pct: Math.max(0, Math.min(100, Math.round(s.pct))), resetsAt: (typeof s.resets_at === 'number' ? s.resets_at : null) }
      : null;
    const fiveHour = seg(o.five_hour), sevenDay = seg(o.seven_day);
    if (!fiveHour && !sevenDay) return null;
    return { fiveHour, sevenDay, t: (typeof o.t === 'number' ? o.t : null) };
  } catch (e) { return null; }
}

// The shared session-order: a persisted JSON array of romp SIDs (first element = top lane / left-most
// chat tab) that the romp-chat-view TABS also read+write, so dragging a tab or a timeline row reorders
// BOTH surfaces. Sessions absent from the list keep the default tier/first-seen order (appended). The
// writer (either surface) persists the full resolved list atomically (tmp+rename); this just reads it.
// [] on a missing/garbage file → pure default order.
function readSessionOrder(node) {
  try {
    const raw = node.fs.readFileSync(node.path.join(stateDir(node), 'session-order.json'), 'utf8');
    const a = JSON.parse(raw);
    return Array.isArray(a) ? a.filter((x) => typeof x === 'string') : [];
  } catch (e) { return []; }
}

// Clean, structured message bodies keyed by romp-msg-id, read from messages.jsonl — postal's source
// of truth (see romp-chat-view/src/postal-spec.ts). romp-events extracts a peer-message TURN PROMPT
// verbatim from the transcript, banner-and-all ("####… 📬 from X · time ####…"); we swap in the clean
// body here, joined by the turn's `mids` (the `<!-- romp-msg-id -->` marker). This is the documented
// id-join — NOT parsing the human-facing banner prose, which postal is free to change.
function messageBodies(node) {
  const out = {};
  try {
    for (const line of node.fs.readFileSync(node.path.join(stateDir(node), 'timeline', 'messages.jsonl'), 'utf8').split('\n')) {
      if (!line) continue;
      let e; try { e = JSON.parse(line); } catch (err) { continue; }
      if (e.ev === 'sent' && e.id && typeof e.body === 'string') out[e.id] = e.body;
    }
  } catch (e) {}
  return out;
}

// ── time parsing (still used by the message/maildir side) ────────────────────
function parseZ(s) {                         // transcript timestamps: ISO-8601 "…Z"
  if (!s) return null;
  const t = Date.parse(s);
  return Number.isNaN(t) ? null : Math.floor(t / 1000);
}
function parseISO(s) {                        // maildir Date: "...T..-0700" or with colon
  if (!s) return null;
  let v = s.trim();
  if (/[+-]\d{4}$/.test(v)) v = v.slice(0, -2) + ':' + v.slice(-2);
  const t = Date.parse(v);
  return Number.isNaN(t) ? null : Math.floor(t / 1000);
}

// ── the single producer: romp-events --emit ─────────────────────────────────
// {now, sessions:{<sid>:{name,color,live,events:[{id,t,end,kind,text,mids,open,summary,reply}],
//  pending:[{id,t,text}]}}}. null on any failure (timeline then shows lanes without bars rather
// than breaking). A disk cache inside romp-events keeps repeated polls cheap (~0.05s warm).
function runRompEvents() {
  return new Promise((resolve) => {
    let node;
    try { node = _node(); } catch (e) { resolve(null); return; }
    node.childProcess.execFile(resolvePython(node.fs), [resolveRompEvents(node), '--emit'],
      { timeout: 6000, windowsHide: true, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024,
        env: Object.assign({}, process.env, { LANG: 'en_US.UTF-8', LC_ALL: 'en_US.UTF-8', LC_CTYPE: 'en_US.UTF-8' }) },
      (err, stdout) => {
        if (err) { resolve(null); return; }
        try { resolve(JSON.parse(stdout)); } catch (e) { resolve(null); }
      });
  });
}

// A session's events + pending (from --emit) → the turn shape the renderer reads. Summaries are
// ALREADY attached per event by id (no binding here). A pending enqueue is a zero-width dot that
// rides `now`; a boundary event is a bar [t, end].
function mapEventsToTurns(events, pending) {
  const out = [];
  for (const e of (events || [])) {
    out.push({ id: e.id || null,                              // romp-events event id (== feed itemId) → canonical join
               start: e.t, end: e.end, prompt: e.text, src: e.kind, mids: e.mids || [],
               pending: false, summary: e.summary || null, reply: e.reply || null,
               tid: e.tid || null, uuid: e.uuid || null,       // deep-link anchors: uuid = prompt/boundary line;
               workUuid: e.workUuid || null,                   // workUuid = period's FIRST assistant line (bar → response; often a thinking block)
               replyUuid: e.replyUuid || null });              // replyUuid = LAST assistant line WITH TEXT = the readable reply (preferred work anchor)
  }
  for (const e of (pending || [])) {
    out.push({ id: e.id || null,
               start: e.t, end: e.t, prompt: e.text, src: 'enqueue', mids: [],
               pending: true, summary: null, reply: null,
               tid: e.tid || null, uuid: e.uuid || null });
  }
  out.sort((a, b) => a.start - b.start);
  return out;
}

// ── state intervals (from the state-transition log tmux-status.sh writes) ──
// Reconstruct every [start,end] the session sat in a given state — a matching entry runs until the
// next transition (or `now`, if it's still in it → a live, open interval). Used for AWAITING
// (permission) candy-stripes and COMPACTING (context compaction, PreCompact→PostCompact) cross-hatch.
// Forward-only — the log starts empty, so periods predating it don't appear.
function stateIntervals(node, sid, now, want) {
  if (!sid) return [];
  const p = node.path.join(stateDir(node), 'states', sid + '.jsonl');
  let text;
  try { text = node.fs.readFileSync(p, 'utf8'); } catch (e) { return []; }
  const ev = [];
  for (const line of text.split('\n')) {
    if (!line) continue;
    try { const o = JSON.parse(line); if (o.t && o.state) ev.push([o.t, o.state]); } catch (e) {}
  }
  ev.sort((a, b) => a[0] - b[0]);
  const cutoff = now - HORIZON, out = [];
  for (let i = 0; i < ev.length; i++) {
    if (ev[i][1] !== want) continue;
    const end = (i + 1 < ev.length) ? ev[i + 1][0] : now;
    if (end < cutoff) continue;
    out.push([Math.max(ev[i][0], cutoff), end]);
  }
  return out;
}
function awaitingIntervals(node, sid, now) { return stateIntervals(node, sid, now, 'permission'); }
function compactingIntervals(node, sid, now) { return stateIntervals(node, sid, now, 'compacting'); }

// All state transitions for a session, sorted by time: [[t, state], …]. Same forward-only log the
// interval builders above read; parsed once so a turn's bar can be clipped to real work (see below).
function stateTransitions(node, sid) {
  if (!sid) return [];
  const p = node.path.join(stateDir(node), 'states', sid + '.jsonl');
  let text;
  try { text = node.fs.readFileSync(p, 'utf8'); } catch (e) { return []; }
  const ev = [];
  for (const line of text.split('\n')) {
    if (!line) continue;
    try { const o = JSON.parse(line); if (o.t && o.state) ev.push([o.t, o.state]); } catch (e) {}
  }
  ev.sort((a, b) => a[0] - b[0]);
  return ev;
}
// When did the session STOP working on the turn that began at `start`? = the first transition OUT of
// an ACTIVE state (working/permission/awaiting/compacting → waiting/idle) strictly after `start`, or
// null if it's still active / the log doesn't cover this period. romp-events ends each turn's bar at
// the NEXT prompt boundary, so a session that died mid-window and was later REVIVED gets its dead
// turn's bar stretched to the revived session's first assistant line — the next boundary is the
// revive prompt ~an hour later, so the whole dead/idle gap paints as one working bar. Capping the bar
// at this idle transition keeps the dead gap blank. (Forward-only log: a turn predating it is left
// uncapped, same limitation as the awaiting/compacting stripes.)
function firstIdleAfter(transitions, start) {
  for (let i = 0; i < transitions.length; i++) {
    if (transitions[i][0] <= start) continue;
    if (!ACTIVE(transitions[i][1])) return transitions[i][0];
  }
  return null;
}
// Start of the session's CURRENT contiguous active run: the most recent transition INTO an active
// state from a non-active one (walking back over consecutive active states), or the first logged
// transition if it's been active throughout. null if the log says it isn't currently active. Used to
// anchor a live bar at WHEN work actually resumed, so a finished-then-idle turn never stretches its
// bar across the intervening gap just because the session later went active again (new prompt /
// compaction) before that new activity hit the transcript.
function lastActiveStart(transitions) {
  const n = transitions.length;
  if (!n || !ACTIVE(transitions[n - 1][1])) return null;
  let i = n - 1;
  while (i > 0 && ACTIVE(transitions[i - 1][1])) i--;
  return transitions[i][0];
}

// Parked/unread mail count for a session. Postal maintains <state>/romp/postal/mail-pending/<sid> IFF
// the session has unread mail in postal/mail/<sid>/new — correct even for DEAD sessions (no tmux vars)
// and survives bus restarts. Presence = has-mail (cheap existsSync gate); count = files in /new. Lets
// the timeline flag a dead recipient that has mail waiting for its revival.
function pendingMail(node, sid) {
  if (!sid) return 0;
  try {
    const base = node.path.join(stateDir(node), 'postal');
    if (!node.fs.existsSync(node.path.join(base, 'mail-pending', sid))) return 0;
    return node.fs.readdirSync(node.path.join(base, 'mail', sid, 'new')).filter((f) => f[0] !== '.').length;
  } catch (e) { return 0; }
}

// ── live tmux sessions → lane metadata (state/context/colour/since), keyed by SID ──
// Keyed by the stable romp-session-id, NOT the name: two live sessions can share a name, and a
// renamed session keeps its id. Name is a display label only.
function liveSessions(node, lines) {
  const sessions = {}, id2name = {};
  for (const line of lines) {
    const p = line.split('|');
    if (p.length < 7 || p[0] !== '1' || !p[1] || !p[2]) continue;
    const name = p[1], sid = p[2], state = p[3], since = p[4], idbg = p[5], summary = p[6];
    const claudeDir = p[7] || '';      // @claude-dir = current cwd; can drift into a subdir mid-session
    let cdir = '';                     // names-file (launch) dir = where the transcript ACTUALLY lives
    const ctxRaw = p[8] || '';
    const context = /^\d+$/.test(ctxRaw) ? Number(ctxRaw) : null;   // context-window fill %
    const model = (p[9] || '').trim();   // @claude-model e.g. "Opus 4.8" (statusline.sh publishes it)
    const effort = (p[10] || '').trim(); // @claude-effort e.g. "xhigh"; may be empty for some models
    let color = idbg && idbg.startsWith('#') ? idbg : '#888888';
    try {
      const parts = node.fs.readFileSync(node.path.join(stateDir(node), 'names', sid), 'utf8').replace(/\n+$/, '').split('\t');
      if (parts.length > 2 && parts[2].startsWith('#')) color = parts[2];
      if (parts.length > 1 && parts[1]) cdir = parts[1];
    } catch (e) {}
    if (!cdir) cdir = claudeDir;       // fall back to @claude-dir only if the names dir is missing
    sessions[sid] = { name, color, state: state || '', since: /^\d+$/.test(since) ? parseInt(since, 10) : null,
                      summary, id: sid, dir: cdir, context, model, effort, live: true };
    id2name[sid] = name;
  }
  return { sessions, id2name };
}

// ── messages: join sent+exec from the log (real latency), maildir fallback ───
function readMessages(node, now, sessions, id2name) {
  const sentEv = {}, execEv = {};
  const msglog = node.path.join(stateDir(node), 'timeline', 'messages.jsonl');
  try {
    for (const line of node.fs.readFileSync(msglog, 'utf8').split('\n')) {
      if (!line) continue;
      let e; try { e = JSON.parse(line); } catch (err) { continue; }
      if (e.ev === 'sent') sentEv[e.id] = e;
      else if (e.ev === 'exec') execEv[e.id] = e.t;
    }
  } catch (e) {}

  // Haiku summaries of message bodies (romp-summarize-backfill), keyed by msg id
  const msgsum = {};
  try {
    for (const line of node.fs.readFileSync(node.path.join(stateDir(node), 'timeline', 'message-summaries.jsonl'), 'utf8').split('\n')) {
      if (!line) continue;
      let o; try { o = JSON.parse(line); } catch (err) { continue; }
      if (o.id && o.summary) msgsum[o.id] = o.summary;
    }
  } catch (e) {}

  const messages = [], seen = new Set();
  for (const mid of Object.keys(sentEv)) {
    const e = sentEv[mid];
    const fromId = e.from_id || '', toId = e.to_id || '';
    if (!(fromId in sessions) || !(toId in sessions)) continue;   // both ends must be known lanes (by sid)
    seen.add(mid);
    if (fromId === toId) continue;   // a session messaging itself isn't a meaningful connector
    const ex = execEv[mid];
    // exec falls back to the SEND time (never the live `now`): a message with no
    // logged delivery is in-flight at its send point, not "landing right now".
    // hasExec records whether the postal log actually delivered it — a delivered
    // message must never be re-derived into a fake pending state. fromId/toId are the
    // lane keys (sids); from/to are display names for the hover label.
    messages.push({ id: mid, fromId, toId, from: id2name[fromId] || e.from, to: id2name[toId],
                    fromOrig: e.from || id2name[fromId] || fromId, sent: e.t, exec: ex || e.t, hasExec: ex != null,
                    parked: !!e.park, text: (e.body || '').trim().slice(0, 240), summary: msgsum[mid] || null, pending: ex == null });
  }

  const mailRoot = node.path.join(stateDir(node), 'postal', 'mail');
  let boxes = [];
  try { boxes = node.fs.readdirSync(mailRoot); } catch (e) {}
  for (const box of boxes) {                          // box dir name = the recipient SID
    const toId = box;
    if (!(toId in sessions)) continue;
    const to = id2name[toId] || toId;
    for (const sub of ['cur', 'new']) {
      const d = node.path.join(mailRoot, box, sub);
      let entries = [];
      try { entries = node.fs.readdirSync(d); } catch (e) { continue; }
      for (const fn of entries) {
        if (seen.has(fn)) continue;
        let txt;
        try { txt = node.fs.readFileSync(node.path.join(d, fn), 'utf8'); } catch (e) { continue; }
        const sep = txt.indexOf('\n\n');
        const head = sep < 0 ? txt : txt.slice(0, sep);
        const body = sep < 0 ? '' : txt.slice(sep + 2);
        const meta = {};
        for (const ln of head.split('\n')) { const i = ln.indexOf(': '); if (i > 0) meta[ln.slice(0, i).toLowerCase()] = ln.slice(i + 2); }
        const fromId = meta['from-id'] || '';
        if (!(fromId in sessions)) continue;
        if (fromId === toId) continue;   // self-message — not a real connector
        const frm = id2name[fromId] || meta['from'] || '?';
        const sent = parseISO(meta['date'] || '') || now;
        messages.push({ id: fn, fromId, toId, from: frm, to, fromOrig: (meta['from'] || frm), sent, exec: sent, hasExec: false, text: body.trim().slice(0, 240), pending: sub === 'new' && (now - sent) < MSG_INFLIGHT_MAX });
      }
    }
  }
  return messages;
}

// ── tmux + assembly ──────────────────────────────────────────────────────────
function listSessionLines() {
  return new Promise((resolve) => {
    let node;
    try { node = _node(); } catch (e) { resolve(null); return; }
    node.childProcess.execFile(resolveTmux(node.fs), ['list-sessions', '-F', TMUX_FORMAT],
      { timeout: 2500, windowsHide: true, encoding: 'utf8',
        env: Object.assign({}, process.env, { LANG: 'en_US.UTF-8', LC_ALL: 'en_US.UTF-8', LC_CTYPE: 'en_US.UTF-8' }) },
      (err, stdout) => {
        if (err && err.code === 'ENOENT') { resolve(null); return; }   // no tmux binary
        resolve((stdout || '').split('\n').filter(Boolean));            // err w/o ENOENT = no server → []
      });
  });
}

function assemble(node, lines, eventsData, now) {
  // (a) live lane metadata from tmux, keyed by name; (b) events from the single producer,
  // keyed by sid (already covers live + ended sessions and merges forks, with summaries bound).
  const tmuxBySid = liveSessions(node, lines || []).sessions;   // keyed by sid
  const evBySid = (eventsData && eventsData.sessions) || {};
  const sessions = {}, id2name = {};   // sessions keyed by SID; id2name = sid → display name
  for (const sid of Object.keys(evBySid)) {
    const es = evBySid[sid], m = tmuxBySid[sid];
    sessions[sid] = {
      name: es.name, id: sid, live: !!es.live,
      color: (m && m.color) || es.color || '#888888',
      state: m ? m.state : '', since: m ? m.since : null,
      context: m ? m.context : null, summary: m ? m.summary : '',
      model: m ? m.model : '', effort: m ? m.effort : '',   // status-bar model+effort (tmux-only, like state/context)
      _events: es.events, _pending: es.pending, _compactions: es.compactions || [],
    };
    id2name[sid] = es.name;
  }
  // A live tmux session --emit didn't return events for (e.g. brand-new, no transcript yet) still
  // gets a lane so its WORKING chip + fallback bar can show. (Keyed by sid → no name clobber.)
  for (const sid of Object.keys(tmuxBySid)) {
    if (sessions[sid]) continue;
    sessions[sid] = Object.assign({}, tmuxBySid[sid], { _events: [], _pending: [], _compactions: [] });
    id2name[sid] = tmuxBySid[sid].name;
  }

  const turns = {};                    // keyed by SID
  const bodyById = messageBodies(node);   // clean peer-message bodies (id → body) for prompt cleanup
  for (const sid of Object.keys(sessions)) {
    const s = sessions[sid];
    let t = mapEventsToTurns(s._events, s._pending);
    // A turn started by a peer message has the raw push (banner + body) as its prompt; swap in the
    // clean structured body, keyed by the turn's romp-msg-id(s). No banner-prose parsing (see
    // messageBodies / postal-spec.ts). The hover/working-on then reads the clean text.
    for (const turn of t) {
      if (!turn.mids || !turn.mids.length) continue;
      for (const mid of turn.mids) { if (bodyById[mid] != null) { turn.prompt = bodyById[mid]; break; } }
    }
    // Clip each completed bar to when work actually STOPPED (firstIdleAfter): romp-events ends a turn
    // at the next prompt boundary, which across a long idle/dead gap (e.g. a revived session whose
    // next prompt is the revive, an hour later) would paint the whole gap as one working bar. The
    // state-transition log is ground truth for when the session left WORKING.
    const trans = stateTransitions(node, sid);
    if (trans.length) {
      for (const turn of t) {
        if (turn.end <= turn.start) continue;             // dots / pending enqueues — nothing to clip
        const idle = firstIdleAfter(trans, turn.start);
        if (idle != null && idle < turn.end) turn.end = Math.max(turn.start, idle);
      }
    }
    // Fallback bar for a live WORKING session with no events yet (just flipped to working, first
    // prompt not logged). Cap how far back it starts so a stale @claude-state-since can't paint
    // phantom hours. Only when there are NO turns.
    if (!t.length && s.live && s.state === 'working' && s.since) {
      t = [{ start: Math.max(s.since, now - 1800), end: now, prompt: s.summary || '(working…)', pending: false, summary: null, reply: null }];
    }
    // A live ACTIVE session is busy right now even if its last assistant line lags (mid tool call /
    // still generating). Run its CURRENT turn's bar to now so it matches the chip — but only when the
    // last recorded turn really IS that in-progress turn. If the session finished a turn, went idle,
    // and THEN became active again (a /compact, or a new prompt whose output isn't in the transcript
    // yet), the last recorded turn ended BEFORE this active run began; stretching it would paint the
    // idle gap + new activity as one long bar on the old turn (the reported compaction/lagging-reply
    // bug). In that case anchor a fresh bar at when work actually resumed instead — and only for real
    // turn WORK ('working'); compaction/awaiting after an idle gap carry their own stripe, no work bar.
    if (s.live && ACTIVE(s.state)) {
      const aStart = lastActiveStart(trans);
      let last = null;
      for (let i = t.length - 1; i >= 0; i--) if (t[i].end > t[i].start) { last = t[i]; break; }
      if (last && (aStart == null || last.end >= aStart - ACTIVE_LAG)) {
        last.end = now;                                  // last turn IS the lagging in-progress one
      } else if (s.state === 'working' && aStart != null) {
        t.push({ start: Math.max(aStart, now - 1800), end: now, prompt: s.summary || '(working…)', pending: false, summary: null, reply: null });
      }
    }
    turns[sid] = t;
  }

  const messages = readMessages(node, now, sessions, id2name);
  // postal logs "exec" at DELIVERY (consume/paste-time); for a busy recipient that's QUEUE time,
  // NOT when the message was worked on. So a logged exec (hasExec) means "landed in the recipient's
  // input", NOT "processed". The true PROCESS-START is the recipient TURN that picked it up:
  // (1) exact id-join via its `<!-- romp-msg-id -->` marker, or (2) a text-heuristic turn (<=1h after
  // send) naming the sender. A message with NEITHER is only "in-flight" (rides `now`) if it PLAUSIBLY
  // hasn't been worked yet — true ONLY when the recipient is live + busy AND the message arrived
  // during/after the recipient's CURRENT turn (not overtaken by a later turn). Otherwise it was
  // processed-but-unbindable or an orphan, and must NOT ride `now` (the old "perpetual just-landing"
  // bug): pin at the log exec if delivered, else at send. hasExec alone NEVER implies pending.
  {
    const idTurn = {};
    for (const n of Object.keys(turns)) {
      for (const t of turns[n]) {
        if (!t.mids) continue;
        for (const mid of t.mids) { const k = mid + '|' + n; if (idTurn[k] == null || t.start < idTurn[k]) idTurn[k] = t.start; }
      }
    }
    const MSG_MAX_LAG = 3600;
    // Each recipient's latest HANDLED moment: a real turn's process-start (a pending enqueue, which
    // has no resolution yet, is excluded). A message that arrived BEFORE this has been overtaken.
    const latestAct = {};
    for (const n of Object.keys(turns)) {
      let mx = 0;
      for (const t of turns[n]) { const v = (t.src === 'enqueue') ? null : t.start; if (v != null && v > mx) mx = v; }
      latestAct[n] = mx;
    }
    const matched = new Set();
    for (const mm of [...messages].sort((a, b) => a.sent - b.sent)) {
      const exact = mm.id ? idTurn[mm.id + '|' + mm.toId] : null;
      if (exact != null) { mm.exec = exact; mm.pending = false; continue; }   // exact id-join → done
      const rturns = (turns[mm.toId] || []).filter((t) => t.src !== 'enqueue');
      let exec = null;
      for (const t of rturns) {
        const key = mm.toId + '|' + t.start;
        if (matched.has(key)) continue;
        if (t.start > mm.sent + MSG_MAX_LAG) break;   // turns are sorted; nothing further can match
        if (t.start >= mm.sent - 5 && t.prompt && (t.prompt.indexOf(mm.fromOrig) !== -1 || t.prompt.indexOf(mm.from) !== -1)) { exec = t.start; matched.add(key); break; }
      }
      if (exec != null) { mm.exec = exec; mm.pending = false; continue; }   // text-heuristic match → true process-start
      // A PARKED message (recipient was offline) logs exec==sent (stamped at REVIVAL, not when it was
      // read) and is usually absent from the recipient's transcript, so id-join/text-match both miss.
      // Don't ride `now` forever (the old bug: a long-since-processed parked msg showed "still landing"):
      // land it at the recipient's first real turn AFTER it was parked — a true post-revival "handled"
      // time, and the long connector then honestly shows the parking delay. Only ride `now` if the
      // recipient hasn't worked at all since (genuinely still in flight). [Exact landing needs postal to
      // log a real revival-delivery exec; tracked with haiku_summaries.]
      if (mm.parked) {
        const rt = (turns[mm.toId] || []).filter((t) => t.src !== 'enqueue' && t.start > mm.sent).sort((a, b) => a.start - b.start)[0];
        if (rt) { mm.exec = rt.start; mm.pending = false; } else { mm.exec = mm.sent; mm.pending = (now - mm.sent) < MSG_INFLIGHT_MAX; }
        continue;
      }
      const rs = sessions[mm.toId] || {};
      // "rides now" only if the recipient is GENUINELY working right now — its active state must be
      // FRESH. A 'working' frozen across a sleep (lid closed mid-turn, no hook flips it) has a stale
      // @claude-state-since; treating it as active is exactly what snaps an old message's connector to
      // the wake `now`. So require the state itself to be recent, not just the message.
      const recipFresh = rs.since != null && (now - rs.since) < MSG_INFLIGHT_MAX;
      if (rs.live && ACTIVE(rs.state) && recipFresh && mm.sent >= (latestAct[mm.toId] || 0) && (now - mm.sent) < MSG_INFLIGHT_MAX) { mm.exec = mm.sent; mm.pending = true; }  // genuinely in-flight → rides `now`
      else if (mm.hasExec) { mm.pending = false; }     // delivered earlier but unbindable/overtaken → pin at log exec
      else { mm.exec = mm.sent; mm.pending = false; }  // never delivered + not in-flight → pin at send
    }
  }
  const out = Object.keys(sessions).map((n) => {
    const s = sessions[n];
    return { name: s.name, color: s.color, state: s.state, live: s.live !== false,
             id: s.id || null,                                // romp session id → deep-link into the chat view
             model: s.model || '', effort: s.effort || '',    // @claude-model/@claude-effort → lane label "Opus 4.8 xhigh"
             context: (s.context != null ? s.context : null),
             since: (s.since != null ? s.since : null),     // state-change time → current awaiting stripe fallback
             awaiting: awaitingIntervals(node, s.id, now),   // historical AWAITING [start,end] spans → candy stripes
             compacting: compactingIntervals(node, s.id, now), // live+historical COMPACTING [start,end] spans → cross-hatch
             pendingMail: pendingMail(node, s.id),            // # unread/parked postal messages → 📬 flag (esp. dead lanes)
             compactions: s._compactions || [] };            // context-compaction markers [{t,prev,meta}] → its own texture
  });
  // Lane order: STABLE so it doesn't reshuffle as sessions flip working↔idle —
  // ordered by first-seen (launch-ish), with ONLY grayed-out sessions (no activity
  // in over an hour, same idea as the dashboard) sunk to the bottom.
  const STALE = 3600;
  const lastAct = {}, firstAct = {};
  for (const n of Object.keys(turns)) {
    let mx = 0, mn = Infinity;
    for (const t of turns[n]) { if (t.end > mx) mx = t.end; if (t.start > mx) mx = t.start; if (t.start < mn) mn = t.start; }
    lastAct[n] = mx; firstAct[n] = mn;
  }
  for (const mm of messages) {
    lastAct[mm.fromId] = Math.max(lastAct[mm.fromId] || 0, mm.sent || 0, mm.exec || 0);
    lastAct[mm.toId] = Math.max(lastAct[mm.toId] || 0, mm.sent || 0, mm.exec || 0);
  }
  // A LIVE session's own state-change time (@claude-state-since) counts as activity,
  // so a freshly-started session with no events yet isn't mistaken for stale.
  for (const n of Object.keys(sessions)) {
    const s = sessions[n];
    if (s.live && s.since) lastAct[n] = Math.max(lastAct[n] || 0, s.since);
  }
  const isStale = (n) => (now - (lastAct[n] || 0)) > STALE;
  const first = (n) => (firstAct[n] != null && firstAct[n] !== Infinity) ? firstAct[n] : 9e15;
  // Three tiers (each then stable first-seen): ACTIVE live on top, ENDED sessions (closed but in
  // window) faded in the MIDDLE, IDLE sessions (live but >1h quiet) faded at the BOTTOM.
  const tier = (s) => (s.live === false) ? 1 : (isStale(s.id) ? 2 : 0);
  out.sort((a, b) => (tier(a) - tier(b)) || (first(a.id) - first(b.id)));
  // User-pinned order (shared with the chat tabs) OVERRIDES the tier default: any SID in
  // session-order.json takes that explicit slot; SIDs not listed keep their tier/first-seen order,
  // appended after. Stable sort (V8) preserves the tier order among unlisted sessions.
  const order = readSessionOrder(node);
  if (order.length) {
    const oidx = new Map(order.map((id, i) => [id, i]));
    const rank = (s) => oidx.has(s.id) ? oidx.get(s.id) : Infinity;
    out.sort((a, b) => rank(a) - rank(b));
  }
  for (const s of out) { s.stale = isStale(s.id); s.faded = (s.live === false) || isStale(s.id); }
  return { now, sessions: out, turns, messages, activeChat: readActiveChat(node), focus: readFocus(node), hover: readHover(node), usage: readUsage(node) };
}

// Resolves to the timeline payload, or { unavailable:true } when there's no tmux /
// node host (mobile). Never rejects. romp-events failing just yields lanes-without-bars.
async function buildTimelineData() {
  let node;
  try { node = _node(); } catch (e) { return { unavailable: true }; }
  const [lines, eventsData] = await Promise.all([listSessionLines(), runRompEvents()]);
  if (lines == null) return { unavailable: true };
  const now = Math.floor(Date.now() / 1000);
  try { return assemble(node, lines, eventsData, now); }
  catch (e) { return { unavailable: true, error: String(e) }; }
}

module.exports = { buildTimelineData, parseZ, parseISO, _assembleForTest: assemble };
