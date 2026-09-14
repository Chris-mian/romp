# Status-line widgets (T409)

The user's ask (2026-09-13, about 3:50 PM PT, paraphrased): like the tab widgets, make the status line's items
customizable widgets. The model, the effort and the context you more or less have to have, so those stay; the folder
and the git branch are widgets that default on; the rest configurable.

This note is the design line, the way the tab widgets went (T379): the points to settle, then served-lab mockups in
both themes for the user's word, then one feature-tier pull request. No code before the word.

## The line today

`#statusline` (render.ts `updateStatusline`) is rebuilt from the active session's record on every push. Left to
right: the session-name chip (an opt-in, `showSessionBadge`, off by default since 2026-09-10), the state chip with
its elapsed timer (Working, Awaiting with its button, Ready, and the transient lines Compacting, Clearing, Opening,
Loading),
then the right cluster `.sl-right`: the folder (basename, full path on hover, a click opens it), the git branch (an
opt-in, `showBranch === true`, off by default since 2026-08-10), the mode, model, effort and fast controls in
`#spinner-meta`, the context battery, and the stop button while busy. A subagent viewer shows a read-only line
instead of all of it.

## 1. The registry

`ui/webview/status-widgets.ts` is one module for both bundles (the chat composes the line from it; the gear renders
each row's live demo from the same render function), mirroring `tab-widgets.ts` term for term:

```ts
export type StatusSlot = "left" | "right";
export interface StatusWidget {
  id: string;            // "folder" | "branch" | "name" | "host" | a contributor's id
  label: string;         // the settings row's name
  description: string;   // one line: what it shows and when
  defaultOn: boolean;
  slot: StatusSlot;      // left: before the state chip; right: leading the right cluster, before the controls
  options?: WidgetOption[];   // the tab widgets' option shape (key, label, choices, default)
  render(s: StatusRecord, opts: Record<string, string>): HTMLElement | null;   // null: nothing on this line
  demo: StatusRecord;    // what the settings row renders over (a synthetic record: proj-web, search-module, TESTHOST)
}
```

`StatusRecord` is the slice of the session record the widgets read: `name`, `color`, `cwd`, `gitBranch`,
`workTree`, `host`, `remote`. The prefs shape is the tab widgets' exactly, `{ on, order, opts }`. The helpers that
normalize prefs, resolve on/off and options and order the registry (`tabWidgetPrefs`, `widgetOn`, `widgetOpts`,
`orderedWidgets`) move unchanged into a shared `widget-prefs.ts` that both registries import: a pure move, so the
T379 pins on those helpers move with it and nothing about the tab widgets changes.

Composition: `updateStatusline` appends the enabled `left` widgets in order before the state chip, then the fixed
left items; the right cluster appends the enabled `right` widgets in order, then the fixed controls. Order is
registration order, then the stored order for the ids it names; drag-to-reorder stays deferred as it did for the tab
widgets. A widget whose render returns null adds nothing (no empty spacer): the host widget on a local session, the
branch widget on a session with no branch.

## 2. The fixed set, never a widget

These stay fixed: the state chip with its timer and the awaiting button; the transient lines (Compacting, Clearing,
Opening, and Loading); the mode, model, effort and fast controls; the context battery; the stop button; the subagent
read-only line.

The fast badge, which the ask listed as a candidate, stays with the controls it sits among: it is a control, not a
mark (a click toggles fast mode), it shows only when the session reports it and the model can run it, and hiding it
would hide a switch the user may need at that moment. If the user wants it configurable all the same, it becomes a
`right` widget, default on, rendered after the controls; the registry allows it.

## 3. The widget set and defaults

| id | slot | default | renders | options |
| --- | --- | --- | --- | --- |
| folder | right | on | the folder glyph and the working directory's basename, full path on hover, a click opens it (today's `.status-dir`) | show: name only (default), full path |
| branch | right | on | the branch glyph and the git branch, the worktree's when the session runs in one (today's `.status-branch`); nothing when no branch is known | none |
| name | left | off | the session's name on its identity colour, before the state chip (today's `chip-session`) | none |
| host | right | on | the host's name for a session on ANOTHER host (a remote session), nothing for a local one, so a local install never sees it | none |

Why the session name defaults off: it duplicates the tab label directly above the line, and the maintainers turned
it off on 2026-09-10 for that reason; it earns its place in split columns, where the user can switch it on. If the
user would rather have it on by default, the same fresh-key rule below covers it. Why the host defaults on: it
renders nothing until a session is remote, and then it is the one fact the line lacks.

Deferred, named so they are not forgotten: a cost or tokens widget (the chat's session record carries no spend
today; the kernel's per-session ledger would have to ride the status first, a kernel change and its own pull
request); a full-path folder is an option above, not a widget. Nothing else on the line today is a candidate: every
other item is a control or a transient.

## 4. Storage, section and entry point

Storage is per browser in `romp:settings` as `settings.statusWidgets = { on, order, opts }`, saved through the gear's
`save()` like every setting, so the same-document `romp:settings` signal repaints the line at once and the kernel's
`settingsSync` fan-out carries it to the other panes and the VS Code copies.

The default flip (the manager's addendum): the branch is off today under `showBranch`, and the user's word makes its
widget default on. Per the fresh-key rule, the widget's preference is a NEW key with its own default and `showBranch`
is its mirror. A store with no `statusWidgets` derives `on.branch` from `showBranch` when that key is present (true:
on; false: off, a reader who turned the branch off stays off), and from the widget's default when it is absent (a
fresh install shows it); every save of the new prefs writes `showBranch` back from `on.branch`, so an older reader
keeps its meaning. The same pair holds for the session name and `showSessionBadge` (present: its value; absent: the
widget's default, off). render.ts reads ONE resolver, `statusWidgetPrefs(settings)`, which applies both mirrors; its
direct reads of `showBranch` and `showSessionBadge` go away, and `settings.ts` normalizes the pair in `loadSettings`
and `saveSettings` exactly as it does `tabWidgets` and `tabCtx`.

The section: a Status line section under the Chat tab, right after Tab widgets (`data-section=statusline`), the
same row grammar (a live demo, the name, the sliding switch, the widget's options as house pickers), one grid across
the rows, descriptions behind the panel's hover popover. The demo is the widget alone, drawn by the line's own render
(the folder glyph and name, the branch, the name chip, the host), the way a tab widget's row shows the widget on a
bare tab.

The entry point: no gear on the line. The chat frame has one gear, the strip's (T405: one glyph, one rows menu), and
its menu gains a third row, "Status line…", opening the settings on Chat scrolled to the new section through the same
`openSettingsOn("chat", "statusline")` relay the Tab widgets row uses; the settings gear reaches the section too, as
it reaches every section. A second gear at the bottom of the same frame would be a second door to the same panel,
and the line has no room to give.

## 5. The rules the tab widgets learned, applied

- No injected default in the gear's `load()` for `statusWidgets`: the reader derives from the mirrors at read time,
  and only a change in the Status line section writes the key (an empty object seeded by `load()` would beat a store
  that carries `showBranch: false`, the T379 round-one high).
- One grid across the widget rows (the `.rs-widgets` rules, reused as they are).
- Descriptions behind the panel's hover popover, placed by the tidy's rule.
- The lab drives the settings through the shell relay (`window.__rompOpenSettings("chat", "statusline")`), never a
  pointer click on the strip under the lifted settings iframe.
- The collision: `gear.js` is under edit in a peer session's master-switch pull request; this pull request adds one
  section and one row builder there and rebases on it.

## Tests

- `ui/webview/status-widgets.test.ts`: the registry and prefs on a tiny DOM (defaults, an unknown id not drawn, the
  order rule, null renders adding nothing, the host widget on a local record).
- `ui/webview/settings.test.ts` additions: the two mirrors in both directions (a store with `showBranch: false` and
  no `statusWidgets` reads the branch off; a save of the prefs writes `showBranch` back; an absent key reads the
  default on).
- `tests/test_statusline_widgets_browser.py`: the served shell, a section reached by the strip gear's row and by the
  relay, a switch off reaching the chat frame's line live, the legacy stores (`showBranch` true, false and absent),
  and the screenshots (`STATUSLINE_SHOTS=<prefix>`) in both themes.
- Pins moved: the T379 helper pins follow the pure move into `widget-prefs.ts`; `session-badge.test.ts` keeps its
  spec.

## Tier

Feature: a self-contained capability inside romp's existing model (a second registry on the pattern of the first,
a settings section, two mirrored keys), no contract change.

## Mockups for the user's word

Served-lab renderings, both themes, in the drops folder under T409: the line as it is today, the line with the
proposed defaults (folder and branch on), the line with every widget on (session name, folder, branch, host on a
remote session), and the Chat tab's Status line section with its four rows. The mockups mutate the served page's own
elements and styles; no product code changed.

## Open for the user

1. The session-name chip: a widget default off (proposed) or on.
2. The fast badge: fixed with the controls (proposed) or a widget default on.
3. The host widget: default on, rendering only for a remote session (proposed).
4. The strip gear's third row as the line's entry point (proposed), or a small gear on the line itself.
