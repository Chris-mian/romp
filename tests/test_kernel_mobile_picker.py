#!/usr/bin/env python3
"""The phone session picker is click-safe and never lets a tap die silently (2026-08-19).

The user could not select a session on the phone: the picker's sync() wiped the list with
innerHTML='' on EVERY kernel push (0.5-3s cadence) — a tap whose finger was down when a push
landed had its row destroyed mid-press (no mousedown/mouseup pair, no click), and the wipe reset
the list's scroll so rows below the fold snapped away mid-reach. Separately, a PLACEHOLDER tab
(session payload not yet merged — a remote host still relaying, a fresh reconnect) painted as a
normal row whose forwarded .click() matched no [data-act] and silently did nothing.

The picker now follows the repo's own click-safety rule: ONE delegated listener on the stable
list, rows updated IN PLACE keyed by data-id (scroll position survives), a pointer-held defer so
a push mid-press flushes on release, and placeholder rows say "syncing" — tapping one marks it
pending ("opening") and the arrival-triggered sync activates it the moment the payload lands.
Source pins on the kernel-served JS/CSS strings."""
import os
import tempfile
import unittest
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
km = load_source("romp_kernel_mpick", os.path.join(BIN, "romp-kernel"))


class MobilePickerClickSafe(unittest.TestCase):
    def test_the_list_is_never_wiped(self):
        self.assertNotIn("list.innerHTML=''", km._CHAT_MOBILE_JS,
                         "a wipe destroys the row under the finger and resets the scroll")
        self.assertIn("if(!row)row=rowMake(s);else rowUpdate(row,s);", km._CHAT_MOBILE_JS,
                      "rows update in place, keyed the strip's way (data-key: the tab's id and the group of its copy)")

    def test_a_reused_row_follows_the_tabs_copy_attribute(self):
        """CI, 2026-09-23: the picker's row key collapses a missing copy attribute and the trail's empty one, so a row made while the
        strip was flat is reused once the strip sections, and rowUpdate never touched data-copy: the reused row kept the missing
        attribute and the picker order lab read the phone's first trail row as a flat-strip row against its own strip's tab. The
        attribute is set (or removed) in rowUpdate, which rowMake calls, so a reused row follows the tab it mirrors.
        tests/test_mobile_picker_order_browser.py executes the reuse in a real browser."""
        js = km._CHAT_MOBILE_JS
        upd = js[js.index("function rowUpdate(row,s){"):js.index("function rowMake(s){")]
        self.assertIn("if(s.copy!==null)row.setAttribute('data-copy',s.copy);else row.removeAttribute('data-copy');", upd,
                      "the copy attribute follows the tab on every update, set or removed")
        mk = js[js.index("function rowMake(s){"):js.index("function headUpdate(row,s){")]
        self.assertNotIn("setAttribute('data-copy'", mk, "one writer: rowMake gets it through the rowUpdate it calls")
        self.assertIn("rowUpdate(row,s);return row;}", mk)

    def test_the_list_mirrors_the_strips_children_headings_and_the_trails_divider_included(self):
        """The phone listed the sessions in another order than the desktop strip once the tabs were grouped
        by tag (the user 2026-09-16): the plan flattened on the phone and the picker scraped that flat strip.
        Now the plan sections there too (tab-groups.ts planStrip; since 2026-09-23 it folds there too) and the picker
        walks the strip's children in order — a heading per group header, a row per tab copy, a divider where
        the untagged trail begins — keyed the strip's way. tests/test_mobile_picker_order_browser.py executes
        it in a real browser against the desktop strip."""
        js, css = km._CHAT_MOBILE_JS, km._CHAT_MOBILE_CSS
        self.assertIn("[].forEach.call(tabs.children,function(t){", js, "the strip's children in order, not a tab query")
        self.assertNotIn("tabs.querySelectorAll('.tab[data-id]')", js)
        self.assertIn("if(t.classList.contains('tab-group-head')&&t.hasAttribute('data-group'))", js, "a heading per group header")
        self.assertIn("if(t.classList.contains('tab-group-sep')){out.push({key:'sep'});return;}", js, "a divider where the trail begins")
        self.assertIn("key:'t:'+id+'/'+(copy===null?'':copy)", js, "a row per COPY: a session under two tags is a row under each")
        self.assertIn("row.appendChild(s.chip.cloneNode(true))", js, "the header's own chip, cloned: one tag treatment")
        self.assertIn("if(!ts[i].id)continue;", js, "the current chip falls back to the first SESSION row, never a heading")
        self.assertIn(".mhead{", css)
        self.assertIn(".msep{", css)
        self.assertNotIn("list.querySelector(", js, "rows are found by key through a map, never a selector (a tag name needs no escaping)")

    def test_a_heading_is_the_fold_control_through_the_strips_own_header(self):
        """The user asked to fold groups on the phone too, the folds shared with the desktop (2026-09-23). That supersedes
        the picker's earlier rule that a heading is a label and nothing folds (#1770, whose reason was that the list is the
        phone's only switcher); the reach is kept by making the heading the control, one tap from the members. The tap
        clicks the strip's own hidden header, the ONE fold path (render.ts toggle-group, which reads the state that header
        rendered), found by walking the strip rather than a selector, and acknowledges at once; the list stays open.
        tests/test_shared_folds_browser.py executes it in a real browser across two devices."""
        js, css = km._CHAT_MOBILE_JS, km._CHAT_MOBILE_CSS
        click = js[js.index("list.addEventListener('click',function(e){"):js.index("list.addEventListener('pointerdown'")]
        self.assertIn("var hd=e.target&&e.target.closest?e.target.closest('.mhead'):null;", click)
        self.assertIn("if(hd){e.stopPropagation();acted(hd);var rh=realHead(hd.getAttribute('data-group'));if(rh){forwarding=true;try{rh.click();}finally{forwarding=false;}}return;}", click,
                      "the strip's header clicked, the tap acknowledged, and propagation stopped: the sync the fold triggers rebuilds "
                      "the heading's contents, and the outside-click check would find the tapped node detached and close the list")
        self.assertIn("document.addEventListener('click',function(e){if(forwarding)return;", js,
                      "…nor may the forwarded click, which bubbles from the hidden strip, outside the list (a real browser caught it)")
        self.assertLess(click.index("'.mhead'"), click.index("'.mrow'"), "the heading is answered before the row lookup")
        self.assertIn("function realHead(g){var hs=tabs.children;", js, "the real header found by walking the strip")
        self.assertNotIn("tabs.querySelector('.tab-group-head", js, "never a selector built from a tag name")
        self.assertIn("el.addEventListener('animationend',function f(){el.classList.remove('romp-acted');", js,
                      "the shared press pulse, cleared on its own end: no timer")
        self.assertIn("if(hd&&(e.key==='Enter'||e.key===' ')){e.preventDefault();hd.click();}", js, "a button to the keyboard too")
        # the heading reads as the desktop header does: chip, caret, count, and folded, the member-state pip
        head = js[js.index("function headUpdate(row,s){"):js.index("function headMake(s){")]
        self.assertLess(head.index("s.chip.cloneNode(true)"), head.index("cv.className='mcaret'"))
        self.assertLess(head.index("cv.className='mcaret'"), head.index("c.className='mcount'"))
        self.assertIn("if(s.folded&&s.pip)row.appendChild(s.pip.cloneNode(true));", head, "a fold hides no needs-you here either")
        self.assertIn("row.setAttribute('aria-expanded',s.folded?'false':'true')", head)
        self.assertIn("if(s.holds)row.setAttribute('aria-current','true');else row.removeAttribute('aria-current');", head,
                      "the heading holding the active session is marked current, as the desktop header is")
        self.assertIn("folded:t.getAttribute('data-folded')==='1'", js, "the fold state the strip's header rendered")
        self.assertIn(".mhead:not(.folded) .mcaret{transform:rotate(90deg)}", css, "the caret turns down while open")
        self.assertIn("min-height:40px", css[css.index(".mhead{"):css.index(".mhead .mcount")], "a tap target a finger lands on")
        self.assertIn("cursor:pointer", css[css.index(".mhead{"):css.index(".mhead .mcount")])

    def test_the_current_session_chip_still_names_a_session_folded_away(self):
        """The active session's group folds like any other (the desktop's rule), so its tab leaves the strip; render.ts
        paints it once more as a hidden `.tab-away` node (tab-groups.ts phoneStandIns) that the current-session chip
        mirrors, and the list never lists it (its group shows the heading alone). Without it the chip fell back to the
        first session in the list: the user must never lose sight of the session they are in."""
        js, css = km._CHAT_MOBILE_JS, km._CHAT_MOBILE_CSS
        self.assertIn("away:t.classList.contains('tab-away')", js)
        self.assertIn("var rows=ts.filter(function(s){return !s.away;});", js, "never a row")
        self.assertIn("rows.forEach(function(s,i){var row=have[s.key];", js, "the list is built from the rows alone")
        self.assertIn("if(ts[i].active){act=ts[i];break;}", js, "the chip reads the active tab, the away node included")
        self.assertIn("#tabs .tab.tab-away{display:none}", css, "never displayed, whatever the layout")

    def test_one_delegated_listener_on_the_stable_list(self):
        self.assertIn("list.addEventListener('click',function(e){", km._CHAT_MOBILE_JS)
        self.assertNotIn("row.addEventListener('click'", km._CHAT_MOBILE_JS,
                         "per-row listeners die with their row — the delegation rule applies here too")

    def test_pushes_defer_while_a_finger_is_down(self):
        self.assertIn("list.addEventListener('pointerdown',function(){held=true;});", km._CHAT_MOBILE_JS)
        self.assertIn("if(held){dirty=true;return;}", km._CHAT_MOBILE_JS)
        self.assertIn("document.addEventListener('pointercancel',release);", km._CHAT_MOBILE_JS)

    def test_a_placeholder_tap_goes_pending_and_activates_on_arrival(self):
        self.assertIn("ph:t.classList.contains('tab-placeholder')", km._CHAT_MOBILE_JS,
                      "the picker knows a not-yet-synced tab when it lists one")
        self.assertIn("pendingId=id;row.classList.add('pending');", km._CHAT_MOBILE_JS,
                      "the tap never dies silently")
        self.assertIn("if(prt&&!prt.classList.contains('tab-placeholder')){pendingId=null;prt.click();hide();}",
                      km._CHAT_MOBILE_JS, "the payload's arrival is the activation event")

    def test_the_rows_say_syncing_and_opening(self):
        self.assertIn(".mrow.ph::after{content:'syncing", km._CHAT_MOBILE_CSS)
        self.assertIn(".mrow.pending::after{content:'opening", km._CHAT_MOBILE_CSS)

    def test_the_trigger_chip_wears_the_chrome_tokens_and_a_light_skin(self):
        """The #mcur/#madd chip is the one mobile surface that never joined the token migration: raw
        #2a2a2a/#3a3a3a in this inline sheet outranked everything styles.css could say, so the chip sat
        as a dark slab on the light chat page (the user 2026-09-02). Surfaces ride tokens whose dark
        value is byte-identical to the old literals; text tiers take light-block overrides, with the
        .colored restatement keeping the identity color on the name."""
        css = km._CHAT_MOBILE_CSS
        self.assertNotIn("background:#2a2a2a", css, "no raw chip surface left — tokens with dark fallbacks")
        self.assertNotIn("border:1px solid #3a3a3a", css)
        self.assertEqual(css.count("background:var(--btn-bg,#2a2a2a)"), 3, "chip, colored chip, and +")
        self.assertEqual(css.count("border:1px solid var(--hairline,#3a3a3a)"), 3,
                         "chip + the '+' + the #mlist card share the one hairline")
        self.assertIn("body.theme-light #mcur{color:var(--menu-fg)}", css)
        self.assertIn("body.theme-light #mcur.colored{color:var(--cbg)}", css)
        self.assertIn("body.theme-light #madd{color:var(--text-muted)}", css)


if __name__ == "__main__":
    unittest.main()
