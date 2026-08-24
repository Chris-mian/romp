// Session views (the user 2026-08-18; TAG model 2026-08-23): the kernel's timeline-views blob,
// echoed on every tabOrder push — which sessions the chat TAB STRIP (and the timeline lanes) show.
// A TAG marks a SPECIALIZED session: tagging it excludes it from the DEFAULT view ("all"), and its
// tag views are where it shows — so "all" = untagged sessions minus the `hidden` set (the manual
// one-off hide). A tagged session is a BACKGROUND session: still running, judged and carded; the
// feed, the + picker, and the "N more" cue keep surfacing it, so nothing runs in secret — the
// 2026-08-11 rule. A tag view shows exactly its members. The kernel's _view_visible is the decision
// of record; this is its client mirror (the timeline carries its own copy — it cannot import TS).
// Pure, split out of render.ts for tests (the time-marker.ts pattern). The kernel emits `tags`;
// `groups` survives in the type as the pre-rename key an un-updated kernel still pushes.
export interface SessionTag { id: string; name?: string; color?: string; members?: string[] }
export interface SessionViews { active?: string; hidden?: string[]; tags?: SessionTag[]; groups?: SessionTag[] }

// the one place the legacy key is honored, so every rule below reads through it
export function viewTags(views: SessionViews | null | undefined): SessionTag[] {
  return (views && (views.tags || views.groups)) || [];
}

export function viewVisible(views: SessionViews | null | undefined, id: string): boolean {
  if (!views || !views.active || views.active === "all") {
    if (views && Array.isArray(views.hidden) && views.hidden.includes(id)) return false;
    return !viewTags(views).some((t) => (t.members || []).includes(id));
  }
  const t = viewTags(views).find((x) => x.id === views.active);
  return t ? (t.members || []).includes(id) : true;
}

// one canonical serialization for echo comparison — the kernel normalizer re-sorts lists and may
// clamp names, so optimistic edits compare by shape, never by identity
export function viewsKey(v: SessionViews | null | undefined): string {
  if (!v) return "";
  return JSON.stringify({ active: v.active || "all",
    hidden: (v.hidden || []).slice().sort(),
    tags: viewTags(v).map((t) => ({ id: t.id, name: t.name, color: t.color,
                                    members: (t.members || []).slice().sort() })) });
}

// hide: add the session to the hidden set — and when the ACTIVE view is a tag that contains it,
// drop it from that tag too, or the gesture is a silent no-op (membership shows it there however
// hidden it is). Other tags keep it: hiding from what you are looking at must not quietly rewrite
// views you are not.
export function hideIn(views: SessionViews | null | undefined, id: string): SessionViews {
  const v: SessionViews = JSON.parse(JSON.stringify(views || {}));
  if (!(v.hidden || []).includes(id)) v.hidden = (v.hidden || []).concat([id]);
  if (v.active && v.active !== "all") {
    const t = viewTags(v).find((x) => x.id === v.active);
    if (t && (t.members || []).includes(id)) t.members = (t.members || []).filter((x) => x !== id);
  }
  return v;
}

// the reveal gesture (re-grounded 2026-08-23 on the TAG model): explicitly opening a session
// SWITCHES the active view to one that shows it and never mutates membership — peeking at a tagged
// worker must not strip its tag. A tagged session's home is its first holder tag (the default view
// never shows it now); an untagged one is unhidden if hidden, and lands on the default view.
export function revealIn(views: SessionViews | null | undefined, id: string): SessionViews {
  const v: SessionViews = JSON.parse(JSON.stringify(views || {}));
  if (viewVisible(v, id)) return v;
  const holder = viewTags(v).find((t) => (t.members || []).includes(id));
  if (holder) { v.active = holder.id; return v; }
  if ((v.hidden || []).includes(id)) v.hidden = (v.hidden || []).filter((x) => x !== id);
  v.active = "all";
  return v;
}
