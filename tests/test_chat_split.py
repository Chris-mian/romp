#!/usr/bin/env python3
"""Chat columns (the user 2026-09-08: several sessions open at once instead of tabbing through them; reworked
2026-09-11 into columns that PARTITION the sessions). The dashboard shell can hold N chat COLUMNS: every column
past the first is a client-made twin of #chat-pane around an iframe at /chat?col=N&skeleton=1 (_LANDING_SPLIT_JS),
a full chat page (its own socket, state blob, drafts and scroll) FILTERED by one shell-owned fact: which sessions
each later column holds, persisted per browser as {v:2, cols:[{n, ids}]}; the first column holds the rest. Two
halves are checked here:

  * SOURCE PINS against the served shell + shim: the column id reaches the state key and the connect query,
    the shell's bridges (picker lift, editor selection, the bell's "session in front", the Log's connection
    tracking, Alt+Arrow, Escape, the gutters) know about later columns, the rail carries no split button, the
    kernel stamps the column and serves a later column as a skeleton client, the partition's functions exist
    and the owner lookup reads no pane's DOM, the parked reveal is addressed and forwarded.
  * EXECUTED: the real _LANDING_SPLIT_JS runs in node against a DOM stub (the test_error_center.py pattern)
    and the whole story is driven — the v1 migration, a move to a new column (the store, the halves, the blob
    seed, no focus posted), a move between columns closing the emptied one, the owner lookup, the emptiness
    message, another dashboard tab's write reconciled, the cross returning sessions home with their drafts,
    drafts travelling on a move, a created session claimed once and never stolen, the restore's seeding, the
    cap, and nothing on the phone — and THE DRAG (DragZonesExecute): a tab drag's zones mounted and unmounted, the
    rectangle's geometry and cue, the drops calling the one mutation, the refused edge at the cap.

Synthetic only — invented sids, no network, no real DOM.
"""
import inspect
import json
import os
import re
import subprocess
import tempfile
import unittest
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
km = load_source("romp_kernel_split", os.path.join(BIN, "romp-kernel"))

WEB = "11111111-2222-3333-4444-555555555501"
API = "11111111-2222-3333-4444-555555555502"
TESTS = "11111111-2222-3333-4444-555555555503"
X = "11111111-2222-3333-4444-555555555509"


class SplitSourcePins(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = km._landing()
        cls.shim = km._shim("chat", 1)

    def test_the_split_script_is_served_after_the_pane_controller_it_leans_on(self):
        self.assertIn("_LANDING_SPLIT_JS", vars(km), "a module-level _JS constant: test_inline_js_parses checks it parses")
        self.assertIn("var CK='romp-chat-cols'", self.html)
        self.assertGreater(self.html.index("var CK='romp-chat-cols'"), self.html.index("window.__rompPaneToggle=togglePane"),
                           "the split runs after the controller: a restored column registers with the gutters and takes a fair "
                           "grow at boot, and a move to a new column from a hidden chat group calls __rompPaneToggle")
        self.assertIn("seed(n,sid);f.src='/chat?col='+n+'&skeleton=1';", km._LANDING_SPLIT_JS,
                      "every later column is /chat?col=N, dialled as a skeleton client of the session its seeded blob names (2026-09-11)")

    def test_the_shim_keys_each_column_s_state_and_names_it_on_the_connect(self):
        # the column comes from the URL; the first column ("" or 1) keeps the unsuffixed key it always had, so no
        # one's persisted active tab, drafts or scroll moves
        self.assertIn('var COL=new URLSearchParams(location.search).get("col")||"";if(COL==="1")COL="";', self.shim)
        self.assertIn('var SK="romp-vscode-state-chat"+(COL?":"+COL:"");', self.shim)
        self.assertIn('(COL?"&col="+encodeURIComponent(COL):"")', self.shim, "the kernel can tell the columns apart in its logs")
        # the ?active= connect hint reads the SAME key, so each column redials with ITS tab first
        self.assertIn('var st0=JSON.parse(localStorage.getItem(SK)||"null");active=(st0&&st0.activeId)||"";', self.shim)
        # …and a later column's FIRST dial has the hint too (2026-09-11): the shell seeds that very key with the session
        # the column opens on before the frame exists, and the frame's src says skeleton=1, which the shim puts on the
        # connect query, so the kernel serves the hinted session whole and the rest as skeleton tabs
        self.assertIn("var BK='romp-vscode-state-chat:';", km._LANDING_SPLIT_JS, "the shell's seed key is the shim's SK for /chat?col=N")
        # the two key strings are ONE string: the shell's prefix is the shim's key plus the shim's separator
        shim_key = re.search(r'var SK="([^"]+)"\+\(COL\?"(:)"\+COL:""\);', self.shim)
        shell_key = re.search(r"var BK='([^']+)';", km._LANDING_SPLIT_JS)
        self.assertEqual(shim_key.group(1) + shim_key.group(2), shell_key.group(1))
        self.assertIn("st.activeId=sid;try{localStorage.setItem(BK+n,JSON.stringify(st));}catch(e){}}", km._LANDING_SPLIT_JS)
        self.assertIn('var SKEL=new URLSearchParams(location.search).get("skeleton")==="1";', self.shim)
        self.assertIn('+((SKEL||(RESTART_DIET&&!everConnected))?"&skeleton=1":"")+(APP==="fleet"?"&provrows=1":""));', self.shim,
                      "the term follows the column; the Outline's capability term (empty for a chat column, plans/outline-pane-provisional-row.md) closes the connect query")
        self.assertIn('+((everConnected&&bundleReady&&readyAcked&&!readyQueued)?"&reconnect=1&proto="+readyProto:"")', self.shim,
                      "the redial gate is untouched (tests/test_pane_shim_return.py runs it)")

    def test_the_kernel_stamps_the_column_on_the_client(self):
        src = inspect.getsource(km.Handler)
        self.assertIn('col = (q.get("col") or [""])[0]', src)
        self.assertIn('if col:\n            client["col"] = col', src)
        with open(os.path.join(BIN, "romp-kernel"), encoding="utf-8") as fh:
            self.assertIn("(wid=%s col=%s slot=%s queued=%dB frame=%dB)", fh.read(), "the drop log names the column")

    def test_a_later_column_s_skeleton_dial_survives_the_ready_arm_s_reset(self):
        # The handshake records both flags: `reconnect` so the pusher cycle that lands before the bundle's ready serves
        # the skeleton set (one full, not the board) into a document that may not hear it; `skeletonOnReady` so the
        # ready arm, whose _client_reset_chat_base pops `reconnect` with the set, can re-arm it for the connect push
        # the page CAN hear (tests/test_chat_skeleton_reconnect.py runs the whole cycle)
        src = inspect.getsource(km.Handler)
        self.assertIn('skeleton = (q.get("skeleton") or [""])[0] == "1"', src)
        self.assertIn('if skeleton:', src)
        # …the survivor only for a FIRST dial: a later column's REDIAL carries skeleton=1 too (the shim reads it off the
        # address on every dial) and its page said ready on an earlier socket, so no arm would ever pop the flag, and
        # armed it left the client unstamped for the page's life (review find 2026-09-11; test_chat_skeleton_reconnect
        # test_09's fourth dial and test_11_c run it)
        self.assertIn('client["reconnect"] = True\n            client["dietSkeleton"] = True\n            if not reconnect:\n                client["skeletonOnReady"] = True', src)   # one string again (2026-09-15): the arm's adjacency, the durable diet marker between the reconnect line and the skeletonOnReady block
        # a pre-ready skeleton client is sent no session frame: the ready arm's connect push is the one full (the strip and
        # the statuses still go; review find 2026-09-11: the full crossed the wire twice per open)
        # …and none while `reconnect` is ARMED either (2026-09-12): a client with the flag has no set yet, and a pusher
        # iteration landing in the ready arm's gap (the set popped, the flag re-armed, the arm's own resolve still ahead)
        # sent a full for a skeleton tab (test_chat_skeleton_reconnect test_11_d runs the gap)
        so = inspect.getsource(km._send_chat_or_status)
        guard = 'if c.get("skeletonOnReady") or c.get("reconnect"):'
        self.assertIn(guard, so)
        self.assertLess(so.index('if sid in (c.get("skeleton") or ()):'), so.index(guard))
        self.assertLess(so.index(guard), so.index('return _send_chat_locked(c, m, ms, change_from, led_changed)'))
        # the flag is re-armed INSIDE the reset, under its lock and right behind its pop of `reconnect` (2026-09-12: as the
        # arm's own two statements past the reset there was an instant with neither flag set), and the reset precedes the
        # arm's connect push
        rs = inspect.getsource(km._client_reset_chat_base)
        self.assertIn('if client.pop("skeletonOnReady", False):\n            client["reconnect"] = True', rs)
        self.assertLess(rs.index("with _client_lock(client):"), rs.index('client.pop("reconnect", None)'))
        self.assertLess(rs.index('client.pop("reconnect", None)'), rs.index('client.pop("skeletonOnReady", False)'))
        i = src.index('msg.get("type") == "ready"')
        body = src[i:i + 3500]
        self.assertNotIn('client.pop("skeletonOnReady"', body, "the arm's own pop and re-arm are gone: the reset's lock holds both")
        self.assertLess(body.index("_client_reset_chat_base(client)"), body.index("self._push_one(client)"))
        # a pre-ready pop (the flag still set) neither stamps the client ready nor lets its caller consume a parked reveal:
        # _reveal_request aims taps at stamped clients, and this page has no listener yet
        rr = inspect.getsource(km._resolve_reconnect)
        self.assertIn('fresh = bool(c.get("skeletonOnReady"))', rr)
        self.assertIn('if not fresh:', rr)
        self.assertLess(rr.index('c.pop("reconnect", False)'), rr.index('fresh = bool(c.get("skeletonOnReady"))'))
        self.assertLess(rr.index('if not fresh:'), rr.index('c["ready"] = True'))
        self.assertEqual(rr.count("return not fresh"), 2, "the no-hint return and the set's return both say whether a REDIAL popped")
        self.assertNotIn("return True", rr)
        # the hand-over is GONE: the seeded blob's activeId is the page's wantActive, so no focus is posted into a NEW frame;
        # a load listener a new frame may carry hands over the moved tab's drafts, never a focus (one for a side column in
        # make(), one for a bottom pane in makeBelow(), same shape)
        split = km._LANDING_SPLIT_JS
        self.assertNotIn("own:true", split)
        self.assertIn("if(state)f.addEventListener('load',function(){adopt(f,sid,state);state=null;});", split)
        self.assertEqual(split.count("addEventListener('load'"), 2)

    def test_the_rail_carries_no_split_button_and_the_menu_no_door(self):
        # a tab is placed by dragging it (the drop zones) or from the palette; a bottom-bar button for it read as
        # clutter (the user 2026-09-08), so the rail and the mobile bar carry none, and the tab menu's item and its
        # openSplit message went with the drag (2026-09-11)
        self.assertNotIn("rail-split", self.html)
        self.assertNotIn("rail-split", km._LANDING_SPLIT_JS)
        self.assertNotIn("openSplit", km._LANDING_SPLIT_JS, "no listener for the menu's ask: the drop zones, the palette and the cross are __rompMoveTab's doors")

    def test_the_drag_s_zones_and_rectangle_are_served_with_their_dress_and_the_light_twin(self):
        split = km._LANDING_SPLIT_JS
        # the page's message is the whole input: the sid rides it, nothing is read from dataTransfer; the geometry is two
        # pure functions; every transition is a pointer crossing
        self.assertIn("if(m.romp==='tabDrag'){", split)
        self.assertNotIn("dataTransfer.getData", split)
        for needle in ["function edgeWidth(w){return Math.max(72,Math.min(180,0.2*w));}",
                       "function ghostRect(pane,rowRect){return {top:rowRect.top,height:rowRect.height,left:pane.left+pane.width/2,width:pane.width/2};}",
                       "function mountZones(){", "function unmountZones(){", "ghost=document.getElementById('col-ghost')",
                       "ghost.textContent=refused?'Four panes at most':drag.name;"]:
            self.assertIn(needle, split, needle)
        self.assertNotIn("setTimeout", split, "nothing is timed")
        # the rectangle's element beside the divider drag's landing line: a child of .col, never a flex item of the row
        self.assertIn("</div><div id=col-ghost></div>", self.html)   # the tab drag's overlay follows the pane row (the divider landing line retired, plans/pane-docking.md section 12)
        # the zones ride the panes (position:relative) above the iframe and the cross (z 7); the edge above the column zone
        self.assertIn(".col-drop{position:absolute;inset:0;z-index:8}", self.html)
        self.assertIn(".col-drop.col-drop-edge{left:auto;z-index:10}", self.html)   # round two LOW c: above the bottom band (z 9) so the edge owns the bottom-right corner
        # the dress: the accent wash (the value --accent-wash resolves to in styles.css) inside a 2 px ring through the token
        self.assertIn(".col-drop.over,#col-ghost{background:rgba(156,210,255,0.12);box-shadow:inset 0 0 0 2px var(--accent,#9cd2ff)}", self.html)
        self.assertIn("#col-ghost{display:none;position:fixed;pointer-events:none;z-index:40;align-items:center;justify-content:center;", self.html)
        self.assertIn("font:600 11px 'Inter',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;color:#8a8a8a;letter-spacing:.04em}", self.html)
        self.assertIn("#col-ghost.on{display:flex}", self.html)
        self.assertIn("#col-ghost.refused{background:transparent;box-shadow:inset 0 0 0 1px var(--accent,#9cd2ff)}", self.html)
        # the light twin beside the cross's, and the refused state restated at the specificity that wins the cascade
        self.assertIn("body.theme-light #col-ghost,body.theme-light .col-drop.over{background:rgba(194,65,12,0.10)}", self.html)
        self.assertIn("body.theme-light #col-ghost.refused{background:transparent}", self.html)
        self.assertLess(self.html.index("body.theme-light #col-ghost,"), self.html.index("body.theme-light #col-ghost.refused"))
        # …and the rectangle's line takes the rail's LIGHT label colour under the light theme (review find 2026-09-11: it
        # kept the dark theme's grey on the cream wash)
        self.assertIn("body.theme-light .rail-btn{color:#5D574E}", self.html)
        self.assertIn("body.theme-light #col-ghost{color:#5D574E}", self.html)
        # a body class toggled for the gesture that nothing read is gone (review find 2026-09-11)
        self.assertNotIn("tabdrag", split)
        self.assertNotIn("tabdrag", self.html)

    def test_the_css_hides_columns_with_the_chat_group_lifts_by_class_and_never_shows_them_on_the_phone(self):
        self.assertIn("body:not(.po-chat) .chat-col,body:not(.po-chat) .gv-chat{display:none}", self.html)
        self.assertIn("body.picker-open .pane.lifted{display:block!important}", self.html)
        self.assertIn("body.picker-open iframe.lifted{display:block;position:fixed;left:0;right:0;top:0;height:var(--app-h,100dvh);z-index:200;background:transparent}", self.html)
        self.assertNotIn("body.picker-open #f-chat{", self.html, "the lift is by class now — a later column's picker lifts THAT column")
        self.assertIn(".chat-col>.col-x{position:absolute;top:4px;right:6px;z-index:7;", self.html)
        mobile = self.html[self.html.index("@media (max-width:820px),(pointer:coarse) and (max-width:1024px){"):]
        self.assertIn(".chat-col,.gv-chat{display:none!important}", mobile)

    def test_the_shell_s_bridges_know_about_later_columns(self):
        # the picker lift marks the ASKING frame (e.source) and its pane
        js = km._LANDING_SETTINGS_JS
        self.assertIn("var lf=(window.__rompFrameOfWin&&window.__rompFrameOfWin(e.source))||document.getElementById('f-chat');", js)
        self.assertIn("Array.prototype.forEach.call(document.querySelectorAll('.lifted'),function(el){el.classList.remove('lifted');});", js)
        self.assertIn("if(m.on&&lf){lf.classList.add('lifted');if(lf.parentElement)lf.parentElement.classList.add('lifted');}", js)
        self.assertIn("document.body.classList.toggle('picker-open',!!m.on);}", js)
        # a passage selected in the feed's viewer lands in the column holding that session, else the one last used
        self.assertIn("fc=(window.__rompChatTarget&&window.__rompChatTarget(m.sid))||fc;", js)
        # the gear's close hands the keyboard back to the column last worked in, else the first (2026-09-11)
        self.assertIn("if(!m.on){var fid=(window.__rompFocusedChatId&&window.__rompFocusedChatId())||'f-chat';"
                      "var fc=document.getElementById(fid)||document.getElementById('f-chat');", js)
        # the bell's "session in front" reads the column last worked in
        self.assertIn("var fid=window.__rompFocusedChatId&&window.__rompFocusedChatId();", km._LANDING_PUSH_JS)
        # the Log tracks a split column's socket under its own key — never masking the first column's
        errs = km._LANDING_ERRS_JS
        self.assertIn("var st={},stc={};", errs)
        self.assertIn("var col=(m.app==='chat'&&window.__rompColOf)?window.__rompColOf(e.source):'';", errs)
        self.assertIn("if(col){var sc=(m.state==='up')?'up':'down',pc=stc[col];stc[col]=sc;", errs)
        self.assertIn("for(var c in stc){if(stc[c]==='down'&&shown('chat'))return true;}", errs)
        self.assertIn("window.__rompColGone=function(c){delete stc[String(c)];paint();};", errs)
        # the first column's tracking is byte-for-byte what it was
        self.assertIn("var s=(m.state==='up')?'up':'down',prev=st[m.app];st[m.app]=s;", errs)
        # Alt+Arrow walks every chat column, the ring follows, later columns are wired as they are made
        focus = km._LANDING_FOCUS_JS
        self.assertIn("window.__rompFocusedChatId=function(){return document.getElementById(lastChat)?lastChat:'f-chat';};", focus)
        self.assertIn("window.__rompWireFocus=function(f){f.addEventListener('load',function(){wire(f);});wire(f);};", focus)
        self.assertIn("function paneOf(id){return PANE[id]||(window.__rompChatPaneOf?window.__rompChatPaneOf(id):null);}", focus)
        self.assertIn("window.__rompWireEsc=function(f){", km._LANDING_ESC_JS)
        # the gutters: later columns register, gv-a/gv-b's left neighbour is the rightmost chat column
        gut = km._LANDING_JS
        self.assertIn("window.__rompRegisterPane=function(id,k){KEYS[id]=k;if(PANES.indexOf(id)<0)PANES.splice(PANES.indexOf('fleet-pane'),0,id);};", gut)
        self.assertIn("window.__rompUnregisterPane=function(id){", gut)
        self.assertIn("function key(id){return KEYS[id]||(id==='chat-pane'?'chat':id==='fleet-pane'?'fleet':id==='feed-pane'?'feed':'files');}", gut)
        self.assertIn("window.__rompGutter=gutter;", gut)
        self.assertIn("gutter('gv-a',function(){return lastChat();},'fleet-pane');", gut)
        # a pane with no grow yet never averages in as NaN (the first split opened 0px wide — review find 2026-09-08),
        # and a column keeps the width it was dragged to across reloads
        self.assertIn(".filter(function(g){return typeof g==='number'&&isFinite(g);});", gut)
        self.assertIn("window.__rompGrowFairIfNew=function(k){if(typeof grow[k]==='number'&&isFinite(grow[k])){setGrow(k,grow[k]);return;}window.__rompGrowFair(k);};", gut)
        # …and a new column takes HALF the rightmost one (2026-09-11), through the gutters' own normalisation
        # (tests/test_pane_gutters.py runs it); the split calls it with the rightmost pane and the new key
        self.assertIn("window.__rompSplitGrow=function(leftId,newKey){", gut)
        self.assertIn("window.__rompSplitShrink=function(leftId,goneId){", gut, "…and its twin: a closing column's pixels go to the column on its left (review find 2026-09-11)")
        split = km._LANDING_SPLIT_JS
        self.assertIn("if(window.__rompSplitGrow)window.__rompSplitGrow(lastPane(),'chat'+n);", split)
        self.assertIn("if(window.__rompGrowFairIfNew)window.__rompGrowFairIfNew('chat'+n);", split)
        # a refused move says why (the acknowledgement rule), and the tab menu can ask first
        self.assertIn("function canSplit(){return !mobile()&&cols.length+1<MAX;}", split)
        self.assertIn("window.__rompCanSplit=canSplit;", split)
        self.assertIn("Four panes at most", split)
        self.assertIn("The phone shows one pane at a time", split)
        self.assertIn("This session is already alone in its column.", split)
        # no hand-over focus (2026-09-11): the seeded blob names the tab, and a later reload of the frame keeps the tab
        # its own state names — the same key, written by the page itself from then on
        self.assertNotIn("{once:true}", split)
        self.assertNotIn("own:true", split)

    def test_the_partition_s_functions_exist_and_the_owner_lookup_reads_no_pane_s_dom(self):
        split = km._LANDING_SPLIT_JS
        # the store's shape and its one-shot migration
        self.assertIn("JSON.stringify({v:2,cols:cols.map(function(c){var o={n:c.n,ids:c.ids.slice()};if(c.place==='below'){o.place='below';o.parent=c.parent;o.ratio=c.ratio;}return o;})})", split)
        self.assertIn("if(Array.isArray(raw)){migrated=true;", split, "a v1 array of numbers is read once more…")
        self.assertIn("if(r0.migrated)save();", split, "…and written back in the new shape")
        # the three pure readers, the sets the pages read, the one mutation, the claim
        for needle in ["function ownerOf(sid){", "function sets(){", "function nextNumber(){",
                       "window.__rompChatSets=function(){return mobile()?null:sets();};",
                       "window.__rompCanSplit=canSplit;window.__rompMoveTab=moveTab;",
                       "window.__rompClaimSession=function(sid,col){", "function moveTab(sid,to,dt){"]:
            self.assertIn(needle, split, needle)
        # the owner lookup is ONE lookup: target() reads the entries, never a pane's active tab; the DOM read survives
        # for the palette's "move this session" alone
        target = re.search(r"function target\(sid\)\{.*?\}\n", split).group(0)
        self.assertNotIn("activeIn(", target)
        self.assertIn("frameOfCol(ownerOf(sid))", target)
        self.assertEqual(split.count("activeIn("), 3, "defined once, called twice (the palette's move to a new column and split-down of the focused column's tab)")
        self.assertIn("activeIn(focused())", split)
        # the emptiness message, the drafts hand-off and the other dashboard tab's write
        self.assertIn("m.romp==='colEmpty'&&Array.isArray(m.gone)", split)
        self.assertIn("f.contentWindow.postMessage({romp:'adopt',sid:sid,state:state},'*');", split)
        self.assertIn("__rompTakeSessionState", split)
        # the page's two answers the shell asks for before it moves a tab or closes a column (review finds 2026-09-11), and
        # the one refusal line each; the movable check at the top of the one mutation, the busy check where a column's
        # last listed member would leave and where a column is closed by hand (a reconcile of another tab's write passes
        # that gate with `keep`, and DEFERS a busy column's close instead, below)
        for needle in ["function movable(f,sid){", "function busy(f){", "function loaded(f){",
                       "var why=refusal(src,sid);if(why==='locked')return notify(LOCKED);if(why||!movable(src,sid))return notify('Only an open session can be moved between columns.');",
                       "var BUSY='A session is still being created in this column.';",
                       "var se2=entry(from);if(se2&&se2.ids.length===1&&closeBusy(from,src))return notify(BUSY);",
                       "function closeBusy(n,f){var kb=belowOf(n);return busy(f)||!!(kb&&busy(frameOfCol(kb.n)));}",
                       "if(!keep&&busy(f)){notify(BUSY);return;}"]:
            self.assertIn(needle, split, needle)
        mt = split[split.index("function moveTab(sid,to,dt){"):split.index("function close(n,keep){")]
        self.assertLess(mt.index("var why=refusal(src,sid);"), mt.index("if(to==='new'){"), "refused before anything is taken or grown (the reason read first, T395)")
        self.assertLess(mt.index("closeBusy(from,src)"), mt.index("var st=take(src,sid)"), "the busy/kid-busy pre-check refused before the hand-off")
        # a peer's write that drops a busy column is deferred, not closed under the create (its queued text died with the
        # document): the entry stays where it was, the number waits, and the page's idle signal closes it against a fresh read
        for needle in ["var deferred={};",
                       "var kb=belowOf(c.n);if(busy(frameOfCol(c.n))||(kb&&busy(frameOfCol(kb.n)))){deferred[c.n]=true;kept.push([i,c]);}else close(c.n,true);});",
                       "kept.forEach(function(k){var e=k[1],o={n:e.n,ids:e.ids.slice()};if(e.place==='below'){o.place='below';o.parent=e.parent;o.ratio=e.ratio;}cols.splice(Math.min(k[0],cols.length),0,o);});",
                       "if(m.romp==='colBusy'&&m.busy===false){var bc=Number(colOf(e.source)),e2=entry(bc),marks=[bc];if(e2&&e2.place==='below')marks.push(e2.parent);var hit=false;marks.forEach(function(mk){if(deferred[mk]){delete deferred[mk];hit=true;}});if(!hit)return;var r=read();if(!r.migrated&&!mobile())reconcile(r.cols);}",
                       "cols.splice(i,1);delete deferred[n];",
                       "var ki=idx(kid.n);if(ki>=0)cols.splice(ki,1);delete deferred[kid.n];"]:   # round four LOW 3: close() clears the KID's deferral too, not just the parent's
            self.assertIn(needle, split, needle)
        # a column closed for emptiness tells the first column which of its gone ids the page's own cross removed, ahead of
        # the store write; nothing else is held (the vanishing tab, 2026-09-12)
        self.assertIn("var crossed=Array.isArray(m.crossed)?gone.filter(function(id){return m.crossed.indexOf(id)>=0;}):[];", split)
        self.assertIn("home.contentWindow.postMessage({romp:'closing',ids:crossed},'*');", split)
        self.assertNotIn("{romp:'closing',ids:gone}", split)
        ce = split[split.index("if(m.romp==='colEmpty'"):split.index("if(m.romp==='orphanState'")]
        self.assertLess(ce.index("{romp:'closing'"), ce.index("close(en.n)"))
        # …and orphaned state offered by a page is handed to the owner's page when that page can hear it
        self.assertIn("if(m.romp==='orphanState'&&Array.isArray(m.sids)){", split)
        self.assertIn("if(t&&t!==sf&&loaded(t))adopt(t,sid,take(sf,sid));", split)
        # a closing column's width goes to the column on its left before its key is dropped (the halving's twin)
        cl = split[split.index("function close(n,keep){"):split.index("function closeFocused(){")]
        self.assertIn("if(window.__rompSplitShrink)window.__rompSplitShrink(leftPane,paneId(n));", cl)
        self.assertLess(cl.index("__rompSplitShrink(leftPane,paneId(n))"), cl.index("__rompUnregisterPane(paneId(n))"))
        self.assertLess(cl.index("var leftPane=si>0?paneId(sideL[si-1].n):'chat-pane',leftFrame=si>0?frameId(sideL[si-1].n):'f-chat';"), cl.index("cols.splice(i,1);"))
        self.assertIn("window.addEventListener('storage',function(e){if(!e||e.key!==CK||mobile())return;var r=read();if(!r.migrated)reconcile(r.cols);});", split)
        # the cross's title reads as what it does now
        self.assertIn("x.title='Close this column';", split)

    def test_the_vertical_split_nests_a_bottom_pane_and_persists_its_placement(self):
        # The chat vertical split (drag a tab to a pane's bottom edge): moveTab(sid,'down',dt) splits a column into a top and
        # a bottom pane, dt the drop target for a drag (else the source column, the keyboard). A bottom pane is a cols entry
        # with place:'below', parent and ratio under v:2; makeBelow
        # nests it inside the parent's .pane as a .chat-sub with a .gh.gh-chat row-resize gutter, WITHOUT reparenting the
        # top iframe (which reloads it); closeBelow un-nests; the horizontal nav skips a bottom pane via __rompChatColumnIds.
        split = km._LANDING_SPLIT_JS
        # persistence carries the placement, still v:2 (an old bundle ignores place/parent/ratio and shows a side column)
        self.assertIn("if(c.place==='below'){o.place='below';o.parent=c.parent;o.ratio=c.ratio;}", split)
        self.assertIn("e.place='below';e.parent=", split, "read() sanitises place/parent/ratio")
        # round four LOW 5: read() DROPS an orphan below entry (parent absent) or a second below on one parent, rather
        # than degrading it to a side column; a degraded entry whose bottom iframe still exists is skipped by make()'s
        # frame-exists guard, so its paneId names a .pane that was never created and lastPane() would break
        self.assertIn("var kidPar={};out=out.filter(function(c){if(c.place!=='below')return true;", split)
        self.assertIn("if(!ok||kidPar[c.parent])return false;kidPar[c.parent]=true;return true;});", split)
        # the one mutation gains a 'down' branch pushing a place:'below' entry keyed on the source column
        self.assertIn("if(to==='down'){var pc=(typeof dt==='number'&&(dt===1||(entry(dt)&&!isBelow(entry(dt)))))?dt:from;", split)
        # the bottom-edge DRAG zone (PR2): a split-down zone per splittable column, its drop passes the target column
        self.assertIn("zone(p,'col-drop-bottom',c.n,function(sid){if(bz.getAttribute('data-refused'))refusePane();else moveTab(sid,'down',c.n);})", split)
        self.assertIn("function ghostRectBottom(pane){", split, "the bottom-half ghost for a split-down drop")
        self.assertIn(".col-drop.col-drop-bottom{top:auto;z-index:9}", self.html)
        # round two MEDIUM: the band is suppressed where moveTab would refuse: a bottom-pane source (fromBelow) or the
        # source's OWN lone column; colSize reads a column's held sessions (the first column's from its page's tabs). The
        # down guard and a busy pre-check (low a) mirror the sideways move; the first column is covered by colSize (low b).
        self.assertIn("function colSize(n){", split)
        self.assertIn(",fromBelow=isBelow(entry(from));", split)
        self.assertIn("if(!belowOf(c.n)&&!fromBelow&&!(c.n===from&&colSize(from)===1)){var bz=zone", split)
        self.assertIn("if(pc===from&&colSize(pc)===1)return notify('This session is already alone in its column.');", split)
        self.assertIn("if(pc!==from){var sfe=entry(from);if(sfe&&sfe.ids.length===1&&closeBusy(from,src))return notify(BUSY);}", split)
        self.assertIn("cols.push({n:nD,ids:[sid],place:'below',parent:pc,ratio:0.5});", split)
        self.assertIn("window.__rompSplitDownChat=function(sid){", split)
        # makeBelow nests without reparenting the top iframe (it flexes in place), adds a .gh.gh-chat gutter and a .chat-sub
        self.assertIn("function makeBelow(ce,sid,state){", split)
        self.assertIn("pp.classList.add('split-v');topf.style.flex=r+' 1 0';", split)
        self.assertIn("g.className='gh gh-chat';", split)
        self.assertIn("sub.className='chat-sub';", split)
        self.assertIn("var ce0=entry(n);if(ce0&&ce0.place==='below')return makeBelow(ce0,sid,state);", split)
        # the vertical gutter trades the two subs' HEIGHT and persists the ratio
        self.assertIn("function gutterV(gid,topId,botId,colN){", split)
        self.assertIn("ce.ratio=nT/sum;save();", split)   # round four LOW 2: persist the exact on-screen fraction (mv already pixel-clamps nT), no fixed-fraction re-clamp that drifts above 1600px
        # closeBelow un-nests: the bottom's sessions rejoin the parent's top, the split-v class and the top flex clear
        self.assertIn("function closeBelow(i,keep){", split)
        self.assertIn("if(isBelow(cols[i]))return closeBelow(i,keep);", split)
        self.assertIn("if(pp)pp.classList.remove('split-v');if(topf)topf.style.flex='';", split)
        # a bottom pane is a vertical child, not a horizontal column: the nav uses a columns-only accessor, and a bottom
        # pane rings its PARENT column (one ring per column)
        self.assertIn("window.__rompChatColumnIds=function(){return columnFrames().map(function(f){return f.id;});};", split)
        self.assertIn("function columnFrames(){", split)
        self.assertIn("function belowOf(n){", split)
        self.assertIn("if(bc&&bc.place==='below')return bc.parent===1?'chat-pane':paneId(bc.parent);", split)
        # the CSS a split column needs: the .pane becomes a column flexbox, each sub wraps its iframe, the top iframe flexes
        self.assertIn(".pane.split-v{display:flex;flex-direction:column}", self.html)
        self.assertIn(".chat-sub{position:relative;flex:1 1 0;min-width:0;min-height:0;overflow:hidden}", self.html)
        self.assertIn(".chat-sub>iframe{position:absolute;inset:0;width:100%;height:100%}", self.html)
        self.assertIn(".pane.split-v>iframe{position:relative;inset:auto;flex:1 1 0;min-height:0}", self.html)   # min-height:0 (like .chat-sub) frees the top from the iframe's ~150px intrinsic floor
        # round two: the gutter resizes the two FLEX children (the top iframe and the .chat-sub), NEVER the bottom
        # iframe (position:absolute, its flex inert), else a drag collapses the pane
        self.assertIn("gutterV(g.id,topId,sub.id,ce.n);", split)
        self.assertNotIn("gutterV(g.id,topId,f.id,ce.n)", split, "the gutter is not wired to the absolute bottom iframe")
        # lastPane skips bottom panes (a bottom pane has no chat-pane-<n>; else the edge zone/gutters/splitGrow get a missing id)
        self.assertIn("function lastPane(){var s=cols.filter(function(c){return !isBelow(c);});return s.length?paneId(s[s.length-1].n):'chat-pane';}", split)
        # the vertical cap refusal counts PANES, not columns
        self.assertIn("function refusePane(){", split)
        self.assertIn("Four panes at most, close one to split.", split)
        self.assertIn("if(!canSplit())return refusePane();", split)
        # the per-half focus ring: __rompTopFrameOf tells a bottom frame from a top, and the CSS rings the focused half
        self.assertIn("window.__rompTopFrameOf=function(fid){", split)
        self.assertIn(".pane.pane-focused.split-v::after{display:none}", self.html)
        self.assertIn(".pane.pane-focused.split-v.focus-top>iframe,.pane.pane-focused.split-v.focus-bottom>.chat-sub{outline:2px solid rgba(156,210,255,0.55);outline-offset:-2px}", self.html)
        # round three, MEDIUM 1 census: EVERY cols neighbour walk routes through sideCols (a bottom pane has no
        # chat-pane-<n>, so cols[i-1]/cols[cols.length-1] would resolve a dead id); the split JS has no raw neighbour walk
        self.assertIn("function sideCols(){return cols.filter(function(c){return !isBelow(c);});}", split)
        self.assertNotIn("cols[i-1]", split, "no raw left-neighbour walk; sideCols resolves the left side column")
        self.assertNotIn("cols[cols.length-1]", split, "no raw last-column walk; sideCols resolves the last side column")
        self.assertIn("var s=sideCols(),si=-1;for(var q=0;q<s.length;q++){if(s[q].n===n){si=q;break;}}return si>0?paneId(s[si-1].n)", split)   # make()'s gutter left neighbour
        self.assertIn("var sc=sideCols();if(!c&&sc.length)c=String(sc[sc.length-1].n);", split)   # closeFocused's fallback
        # round three, MEDIUM 2: a parent whose nested pane is busy is deferred like a busy column; the bottom pane's idle clears the parent's mark
        self.assertIn("var kb=belowOf(c.n);if(busy(frameOfCol(c.n))||(kb&&busy(frameOfCol(kb.n)))){deferred[c.n]=true;kept.push([i,c]);}else close(c.n,true);});", split)
        self.assertIn("e2=entry(bc),marks=[bc];if(e2&&e2.place==='below')marks.push(e2.parent);", split)
        # round four LOW 2: the persisted ratio is the exact on-screen fraction; restore and read accept any proper
        # fraction (0<f<1), the pixel minimum living only in mv()'s clamp, so a legitimately small ratio is not reset to 0.5
        self.assertIn("e.ratio=(r>0&&r<1)?r:0.5;", split)
        self.assertIn("var r=(ce.ratio>0&&ce.ratio<1)?ce.ratio:0.5;", split)

    def test_the_parked_push_tap_reveal_is_addressed_to_the_client_that_consumes_it_and_forwarded_by_the_page(self):
        # one chat client consumes the parked tap (_consume_pending_reveal), so it rides `own`; under the partition the
        # consuming page hands a tap for a session another column holds to that column, without `own` (render.ts)
        src = inspect.getsource(km._consume_pending_reveal)
        self.assertIn('m["own"] = True', src)
        self.assertIn("posts the same message WITHOUT `own` into", src)
        self.assertIn("one hop by construction", src)
        self.assertNotIn("a state the split allows on purpose", src, "two columns on one session is no longer a state the split allows")
        self.assertIn("client[\"send\"](json.dumps(m))", src)


# ── the split script, RUN ────────────────────────────────────────────────────────────────────────────
HARNESS = r"""
'use strict';
let STORE = {};
const CALLS = { register: [], unregister: [], growFair: [], splitGrow: [], splitShrink: [], gutter: [], wireFocus: [], wireEsc: [], colGone: [], events: [], posted: [], focus: [], notify: [], toggle: [], taken: [], sets: [] };
let SEQ = [];             // the order of the shell's side effects across stubs (a store write, a post, a grow, a key drop)
let UNMOVABLE = new Set(); // ids the pages answer "not a session a column can hold" for (a create in flight, a viewer)
let LOCKED_SIDS = new Set(); // ids whose page answers 'locked' (the tab lock, T395): the toast names the gear's menu (T405)
let BUSY = {};            // frame id → whether that page reports a create in flight
global.localStorage = { getItem: (k) => (k in STORE ? STORE[k] : null), setItem: (k, v) => { STORE[k] = String(v); CALLS.sets.push(k); SEQ.push('set:' + k); }, removeItem: (k) => { delete STORE[k]; } };
let BODY_CLASSES = new Set(['po-chat', 'po-feed', 'po-timeline']);
let FOCUSED = 'f-chat';   // what the shell's focus script would report as the column last worked in
let MOBILE = false;       // whether #mtabs is displayed (the phone layout)
let BYID = {};
let WL = {};
let TAKE = {};            // frame id → sid → what that page holds for the session (its __rompTakeSessionState answer)
function mkEl(tag) {
  const el = {
    tagName: tag, className: '', title: '', textContent: '', src: '', parentElement: null, _id: '',
    style: { flex: '', _props: {}, setProperty(k, v) { this._props[k] = v; }, removeProperty(k) { delete this._props[k]; } },
    _attrs: {}, _ls: {}, children: [], _active: '',
    _rect: { left: 0, top: 0, width: 0, height: 0 }, getBoundingClientRect() { return Object.assign({}, this._rect); },
    contains(n) { return n === this || this.children.some((c) => c.contains && c.contains(n)); },
    setAttribute(k, v) { this._attrs[k] = String(v); },
    getAttribute(k) { return k in this._attrs ? this._attrs[k] : null; },
    appendChild(c) { c.parentElement = this; this.children.push(c); return c; },
    insertBefore(c, ref) { c.parentElement = this; const i = this.children.indexOf(ref); if (i < 0) this.children.push(c); else this.children.splice(i, 0, c); return c; },
    remove() { const p = this.parentElement; if (p) { const i = p.children.indexOf(this); if (i >= 0) p.children.splice(i, 1); }
      const drop = (n) => { if (n._id) delete BYID[n._id]; n.children.forEach(drop); }; drop(this); this.parentElement = null; },
    addEventListener(k, f, opts) { (this._ls[k] = this._ls[k] || []).push({ f, once: !!(opts && opts.once) }); },
    fire(k, ev) { const ls = (this._ls[k] || []).slice(); this._ls[k] = ls.filter((l) => !l.once); ls.forEach((l) => l.f(ev || { stopPropagation() {} })); },
  };
  Object.defineProperty(el, 'id', { get() { return this._id; }, set(v) { if (this._id) delete BYID[this._id]; this._id = String(v); if (v) BYID[v] = this; } });
  Object.defineProperty(el, 'offsetHeight', { get() { return this._rect.height; }, configurable: true });   // gutterV reads offsetHeight for the split's pixel clamp
  const cls = () => el.className.split(/\s+/).filter(Boolean);
  el.classList = {
    contains: (c) => cls().includes(c),
    add: (...cs) => { const l = cls(); cs.forEach((c) => { if (!l.includes(c)) l.push(c); }); el.className = l.join(' '); },
    remove: (...cs) => { el.className = cls().filter((c) => !cs.includes(c)).join(' '); },
    toggle: (c, force) => { const want = force === undefined ? !cls().includes(c) : !!force; if (want) el.classList.add(c); else el.classList.remove(c); return want; },
  };
  if (tag === 'iframe') {
    el.contentWindow = {
      postMessage(m) { CALLS.posted.push({ id: el.id, m }); SEQ.push('post:' + el.id + ':' + (m.romp || m.type)); }, focus() { CALLS.focus.push(el.id); },
      __rompTakeSessionState(sid) { const held = TAKE[el.id] && TAKE[el.id][sid]; CALLS.taken.push([el.id, sid, !!held]); if (!held) return null; delete TAKE[el.id][sid]; return held; },
      __rompMovableSession(sid) { return !UNMOVABLE.has(sid) && !LOCKED_SIDS.has(sid); },
      __rompMoveRefusal(sid) { return LOCKED_SIDS.has(sid) ? 'locked' : UNMOVABLE.has(sid) ? 'not-open' : ''; },
      __rompColumnBusy() { return !!BUSY[el.id]; },
    };
    el.contentDocument = { querySelector(sel) { return (sel === '#tabs .tab.active[data-id]' && el._active) ? { getAttribute: () => el._active } : null; },
      querySelectorAll(sel) { return (sel === '#tabs .tab[data-id]') ? (el._tabs || []) : []; } };   // colSize(1) counts the first column's tabs; _tabs unset => 0 => "not lone"
  }
  return el;
}
let ROW = null;
global.document = {
  body: { classList: { contains: (c) => BODY_CLASSES.has(c), add: (c) => BODY_CLASSES.add(c), remove: (c) => BODY_CLASSES.delete(c) } },
  querySelector(sel) { return sel === '.row' ? ROW : null; },
  getElementById(id) { return BYID[id] || null; },
  createElement(tag) { return mkEl(tag); },
};
global.getComputedStyle = (el) => ({ display: el === BYID['mtabs'] ? (MOBILE ? 'flex' : 'none') : 'block' });
global.window = global;
window.__rompPaneSourceOk = () => true;   // the shell's source check (the boot script's, plans/panes-as-data.md): this stub's posts stand for a protocol pane's
global.addEventListener = (t, f) => { (WL[t] = WL[t] || []).push(f); };
global.removeEventListener = (t, f) => { if (WL[t]) WL[t] = WL[t].filter((g) => g !== f); };   // gutterV's up() detaches its live mousemove/mouseup
global.dispatchEvent = (ev) => { CALLS.events.push(ev); (WL[ev.type] || []).forEach((f) => f(ev)); return true; };
global.CustomEvent = class { constructor(type, o) { this.type = type; this.detail = (o || {}).detail; } };
global.__rompRegisterPane = (id, k) => CALLS.register.push([id, k]);
global.__rompUnregisterPane = (id) => { CALLS.unregister.push(id); SEQ.push('unregister:' + id); };
global.__rompSplitShrink = (left, gone) => { CALLS.splitShrink.push([left, gone]); SEQ.push('shrink:' + gone); return true; };   // the gutters' hand-back (tests/test_pane_gutters.py runs the real one)
global.__rompGrowFair = (k) => CALLS.growFair.push('fair:' + k);
global.__rompGrowFairIfNew = (k) => CALLS.growFair.push(k);   // what the split calls: fair only when the store holds nothing
global.__rompSplitGrow = (left, key) => { CALLS.splitGrow.push([left, key]); return true; };   // the gutters' halving (tests/test_pane_gutters.py runs the real one)
global.__rompNotify = (kind, text) => CALLS.notify.push([kind, text]);
global.__rompPaneToggle = (k, to) => CALLS.toggle.push([k, to]);
global.__rompGutter = (gid, leftPick, rightId) => CALLS.gutter.push({ gid, leftPick, rightId });
global.__rompWireFocus = (f) => CALLS.wireFocus.push(f.id);
global.__rompWireEsc = (f) => CALLS.wireEsc.push(f.id);
global.__rompColGone = (c) => CALLS.colGone.push(c);
global.__rompFocusedChatId = () => FOCUSED;
function boot(store, mobile) {
  STORE = Object.assign({}, store || {}); MOBILE = !!mobile; BYID = {}; WL = {}; TAKE = {}; FOCUSED = 'f-chat'; BODY_CLASSES = new Set(['po-chat', 'po-feed', 'po-timeline']);
  SEQ = []; UNMOVABLE = new Set(); LOCKED_SIDS = new Set(); BUSY = {};
  for (const k in CALLS) CALLS[k] = [];
  ROW = mkEl('div'); ROW.className = 'row';
  const cp = mkEl('div'); cp.id = 'chat-pane'; const fc = mkEl('iframe'); fc.id = 'f-chat'; cp.appendChild(fc); ROW.appendChild(cp);
  const gva = mkEl('div'); gva.id = 'gv-a'; ROW.appendChild(gva);
  const fp = mkEl('div'); fp.id = 'fleet-pane'; ROW.appendChild(fp);
  const gvb = mkEl('div'); gvb.id = 'gv-b'; ROW.appendChild(gvb);
  const fd = mkEl('div'); fd.id = 'feed-pane'; ROW.appendChild(fd);
  const mt = mkEl('nav'); mt.id = 'mtabs';
  const cg = mkEl('div'); cg.id = 'col-ghost';   // the rectangle's element: a sibling of the row in the served markup, never a flex item of it
  ROW._rect = { left: 0, top: 30, width: 1400, height: 800 };
  (0, eval)(SPLIT_JS);
}
const SPLIT_JS = __SPLIT_JS__;
function order() { return ROW.children.map((c) => c.id); }
function ids() { return window.__rompChatFrameIds(); }
function cols() { return JSON.parse(STORE['romp-chat-cols'] || 'null'); }
function blob(n) { return JSON.parse(STORE['romp-vscode-state-chat:' + n] || 'null'); }
function saves() { return CALLS.sets.filter((k) => k === 'romp-chat-cols').length; }
function tgt(sid) { const f = window.__rompChatTarget(sid); return f ? f.id : null; }
function crossOf(fid) { return BYID[fid].parentElement.children.filter((c) => c.className === 'col-x')[0]; }
function msg(data, fromId) { window.dispatchEvent({ type: 'message', data, source: fromId ? BYID[fromId].contentWindow : null }); }
"""

DRIVER = r"""
const out = {};
const WEB = '11111111-2222-3333-4444-555555555501', API = '11111111-2222-3333-4444-555555555502', TESTS = '11111111-2222-3333-4444-555555555503', X = '11111111-2222-3333-4444-555555555509';
// A) a fresh desktop dashboard: one column, nothing made, every session the first column's
boot({}, false);
out.fresh = { ids: ids(), order: order(), lastPane: window.__rompLastChatPane(), sets: window.__rompChatSets(), stored: STORE['romp-chat-cols'] || null,
              targetUnknown: tgt(X), targetNone: tgt(''), saves: saves() };
// B) the v1 store (a bare array of column numbers) migrates once: a number whose blob names a session becomes that
//    session's column; a number with no session is dropped; the v2 shape is written back
boot({ 'romp-chat-cols': '[2]', 'romp-vscode-state-chat:2': JSON.stringify({ activeId: WEB, scroll: 4 }) }, false);
out.migrated = { ids: ids(), stored: cols(), blob2: blob(2), sets: window.__rompChatSets(), posted: CALLS.posted.slice(), saves: saves(), srcs: [BYID['f-chat-2'].src] };
boot({ 'romp-chat-cols': '[2,5]', 'romp-vscode-state-chat:2': JSON.stringify({ activeId: WEB }), 'romp-vscode-state-chat:5': '{}' }, false);
out.migratedDrop = { ids: ids(), stored: cols() };
// C) the moves. A session to a NEW column: the store, the halves, the blob seed, no focus posted, the ring there
boot({}, false);
const f2 = window.__rompMoveTab(API, 'new'); f2.fire('load'); f2.fire('load');
out.moved = { id: f2.id, src: f2.src, col: f2.getAttribute('data-col'), pane: f2.parentElement.id, paneCls: f2.parentElement.className, flex: f2.parentElement.style.flex,
              order: order(), stored: cols(), sets: window.__rompChatSets(), blob2: blob(2), splitGrow: CALLS.splitGrow.slice(), growFair: CALLS.growFair.slice(),
              register: CALLS.register.slice(), wireFocus: CALLS.wireFocus.slice(), wireEsc: CALLS.wireEsc.slice(),
              gutter: CALLS.gutter.map((g) => ({ gid: g.gid, left: g.leftPick(), right: g.rightId })),
              event: CALLS.events.filter((e) => e.type === 'romp-chat-cols').map((e) => ({ col: e.detail.col, open: e.detail.open, frame: e.detail.frame && e.detail.frame.id })),
              posted: CALLS.posted.slice(), focused: CALLS.focus.slice(), taken: CALLS.taken.slice(), crossTitle: crossOf('f-chat-2').title,
              targetApi: tgt(API), targetTests: tgt(TESTS), canSplit: window.__rompCanSplit(), ids: ids(), lastPane: window.__rompLastChatPane(),
              paneOf: window.__rompChatPaneOf('f-chat-2'), colOf: window.__rompColOf(f2.contentWindow), frameOfWin: window.__rompFrameOfWin(f2.contentWindow) === f2 };
// a second new column halves the RIGHTMOST one; then a move BETWEEN later columns closes the emptied origin
const f3 = window.__rompMoveTab(TESTS, 'new');
out.third = { id: f3.id, splitGrow: CALLS.splitGrow.slice(), stored: cols(), gutterLeft3: CALLS.gutter.filter((g) => g.gid === 'gv-chat-3')[0].leftPick(), order: order() };
CALLS.posted = []; CALLS.focus = []; CALLS.unregister = []; CALLS.colGone = []; CALLS.taken = [];
const t3 = window.__rompMoveTab(API, 3);
out.movedInto3 = { target: t3 && t3.id, ids: ids(), order: order(), stored: cols(), sets: window.__rompChatSets(), posted: CALLS.posted.slice(), focused: CALLS.focus.slice(),
                   unregister: CALLS.unregister.slice(), colGone: CALLS.colGone.slice(), taken: CALLS.taken.slice(),
                   targetApi: tgt(API), targetTests: tgt(TESTS), targetWeb: tgt(WEB),
                   closedEvent: CALLS.events.filter((e) => e.type === 'romp-chat-cols' && e.detail.open === false).map((e) => e.detail.col) };
FOCUSED = 'f-chat-77'; out.movedInto3.stale = tgt('');   // a stale focus id (its column is gone): the first column
FOCUSED = 'f-chat-3'; out.movedInto3.focusedNone = tgt('');   // no session named: the column last worked in
FOCUSED = 'f-chat';
// …and HOME (the first column, which derives): the origin keeps its other member
CALLS.posted = []; CALLS.focus = [];
const t1 = window.__rompMoveTab(API, 1);
out.movedHome = { target: t1 && t1.id, ids: ids(), stored: cols(), sets: window.__rompChatSets(), posted: CALLS.posted.slice(), focused: CALLS.focus.slice(), targetApi: tgt(API) };
// refusals, each with its line or a null: alone in its column, no such column, no session, already there
CALLS.notify = []; CALLS.posted = []; CALLS.sets = [];
out.refused = { alone: window.__rompMoveTab(TESTS, 'new'), noSuch: window.__rompMoveTab(API, 7), noSid: window.__rompMoveTab('', 'new'),
                same: (window.__rompMoveTab(TESTS, 3) || {}).id, sameHome: (window.__rompMoveTab(API, 1) || {}).id,
                notify: CALLS.notify.slice(), stored: cols(), posted: CALLS.posted.length, saves: saves() };
// the palette's move: nothing active says so; the focused column's active tab moves to a new column (the lowest free number)
CALLS.notify = []; BYID['f-chat']._active = '';
out.paletteNone = { r: window.__rompSplitChat(), notify: CALLS.notify.slice() };
BYID['f-chat']._active = WEB; CALLS.notify = []; BODY_CLASSES.delete('po-chat'); CALLS.toggle = [];
const fp = window.__rompSplitChat();
out.paletteMove = { id: fp && fp.id, stored: cols(), notify: CALLS.notify.slice(), toggle: CALLS.toggle.slice(), blob2: blob(2) };
BODY_CLASSES.add('po-chat');
// D) EMPTINESS: a column's page says which members the kernel no longer lists; the entry is pruned, and closes only when empty
boot({}, false);
window.__rompMoveTab(API, 'new'); window.__rompMoveTab(TESTS, 2);
CALLS.sets = []; CALLS.unregister = [];
msg({ romp: 'colEmpty', gone: [TESTS] }, 'f-chat-2');
out.colEmptyPartial = { ids: ids(), stored: cols(), saves: saves() };
msg({ romp: 'colEmpty', gone: [API] }, 'f-chat');   // from a page with no entry (the first column): ignored
out.colEmptyIgnored = { ids: ids(), stored: cols() };
window.__rompMoveTab(X, 2);   // a member added meanwhile…
msg({ romp: 'colEmpty', gone: [API] }, 'f-chat-2');   // …keeps the column open when the others go
out.colEmptyKept = { ids: ids(), stored: cols() };
msg({ romp: 'colEmpty', gone: [X] }, 'f-chat-2');
out.colEmptyAll = { ids: ids(), stored: cols(), unregister: CALLS.unregister.slice() };
// E) another dashboard tab's write reconciles: what it added is made (seeded like a restore), what it dropped closes, nothing is written back
boot({ 'romp-chat-cols': JSON.stringify({ v: 2, cols: [{ n: 2, ids: [WEB] }] }) }, false);
CALLS.sets = []; CALLS.posted = [];
STORE['romp-chat-cols'] = JSON.stringify({ v: 2, cols: [{ n: 2, ids: [WEB] }, { n: 4, ids: [API, TESTS] }] });
STORE['romp-vscode-state-chat:4'] = JSON.stringify({ activeId: TESTS, scroll: 9 });
window.dispatchEvent({ type: 'storage', key: 'romp-chat-cols' });
out.reconciled = { ids: ids(), order: order(), sets: window.__rompChatSets(), saves: saves(), blob4: blob(4), stored: STORE['romp-chat-cols'], posted: CALLS.posted.slice() };
STORE['romp-chat-cols'] = JSON.stringify({ v: 2, cols: [{ n: 4, ids: [API, TESTS] }] });
window.dispatchEvent({ type: 'storage', key: 'romp-chat-cols' });
out.reconciledClose = { ids: ids(), sets: window.__rompChatSets(), saves: saves(), unregister: CALLS.unregister.slice() };
window.dispatchEvent({ type: 'storage', key: 'romp-pane-grow' });   // another key: nothing
out.reconciledOther = { ids: ids() };
// F) the CROSS returns the column's sessions home, drafts and all
boot({}, false);
window.__rompMoveTab(API, 'new'); window.__rompMoveTab(TESTS, 2);
TAKE['f-chat-2'] = { [API]: { draft: 'a draft for api', citations: [], files: [], staged: [] } };
CALLS.posted = []; CALLS.taken = [];
crossOf('f-chat-2').fire('click', { stopPropagation() {} });
out.cross = { ids: ids(), stored: cols(), sets: window.__rompChatSets(), posted: CALLS.posted.slice(), taken: CALLS.taken.slice(), targetApi: tgt(API), targetTests: tgt(TESTS) };
// G) DRAFTS TRAVEL on a move: to a new column on its load, once; into an open column at once, ahead of the focus
boot({}, false);
TAKE['f-chat'] = { [TESTS]: { draft: 'typed in column one', citations: [{ title: 'a card' }], files: ['/tmp/a.png'], staged: [] } };
CALLS.posted = []; CALLS.taken = [];
const fn2 = window.__rompMoveTab(TESTS, 'new');
out.draftsNew = { id: fn2.id, postedBeforeLoad: CALLS.posted.slice(), taken: CALLS.taken.slice() };
fn2.fire('load'); out.draftsNew.postedAfterLoad = CALLS.posted.slice();
fn2.fire('load'); out.draftsNew.postedAfterSecondLoad = CALLS.posted.length;
const fo = window.__rompMoveTab(WEB, 'new');   // column 3, holding WEB
CALLS.posted = []; CALLS.taken = [];
TAKE['f-chat-2'] = { [TESTS]: { draft: 'more', citations: [], files: [], staged: [{ text: 's', cites: [] }] } };
const to3 = window.__rompMoveTab(TESTS, 3);
out.draftsOpen = { target: to3 && to3.id, posted: CALLS.posted.slice(), taken: CALLS.taken.slice(), ids: ids(), stored: cols() };
// H) a session CREATED from a later column is claimed for it, once, and never stolen from a column that lists it
boot({}, false);
window.__rompMoveTab(API, 'new'); window.__rompMoveTab(WEB, 'new');
out.claim = { first: window.__rompClaimSession(X, 2), again: window.__rompClaimSession(X, 2), steal: window.__rompClaimSession(X, 3), listed: window.__rompClaimSession(API, 3),
              noSid: window.__rompClaimSession('', 2), noCol: window.__rompClaimSession(TESTS, 9), stored: cols(), targetX: tgt(X) };
// I) the RESTORE seeds each column's blob with the tab it names when that is still a member, else its first member
boot({ 'romp-chat-cols': JSON.stringify({ v: 2, cols: [{ n: 2, ids: [WEB, API] }, { n: 5, ids: [TESTS] }] }), 'romp-vscode-state-chat:2': JSON.stringify({ activeId: API, scroll: 3 }) }, false);
out.restored = { ids: ids(), order: order(), blob2: blob(2), blob5: blob(5), posted: CALLS.posted.slice(), sets: window.__rompChatSets(), saves: saves(),
                 srcs: [BYID['f-chat-2'].src, BYID['f-chat-5'].src], lastPane: window.__rompLastChatPane(), growFair: CALLS.growFair.slice(), splitGrow: CALLS.splitGrow.slice(),
                 nextNumber: (window.__rompMoveTab(X, 'new') || {}).id };
boot({ 'romp-chat-cols': JSON.stringify({ v: 2, cols: [{ n: 2, ids: [WEB, API] }] }), 'romp-vscode-state-chat:2': JSON.stringify({ activeId: TESTS }) }, false);
out.restoredMovedAway = { blob2: blob(2) };
// a corrupt store: nothing made, nothing thrown
boot({ 'romp-chat-cols': 'not json{' }, false);
out.corrupt = { ids: ids(), stored: STORE['romp-chat-cols'] };
boot({ 'romp-chat-cols': JSON.stringify({ v: 2, cols: [{ n: 2, ids: [] }, { n: 'x', ids: [WEB] }, { n: 3, ids: [API, API] }, { n: 4, ids: [API] }] }) }, false);
out.sanitised = { ids: ids(), sets: window.__rompChatSets() };
// J) four columns at most
boot({}, false);
window.__rompMoveTab(WEB, 'new'); window.__rompMoveTab(API, 'new'); window.__rompMoveTab(TESTS, 'new');
CALLS.notify = [];
out.cap = { ids: ids(), fourth: window.__rompMoveTab(X, 'new'), notify: CALLS.notify.slice(), canSplit: window.__rompCanSplit(), stored: cols() };
// K) the phone: nothing is restored, the one chat filters nothing, a move is refused, the store keeps the desktop's arrangement
const PHONE_STORE = JSON.stringify({ v: 2, cols: [{ n: 2, ids: [WEB] }] });
boot({ 'romp-chat-cols': PHONE_STORE }, true);
out.mobile = { ids: ids(), sets: window.__rompChatSets(), moved: window.__rompMoveTab(WEB, 'new'), order: order(), notify: CALLS.notify.slice(), canSplit: window.__rompCanSplit(),
               stored: STORE['romp-chat-cols'], storedWas: PHONE_STORE, saves: saves(), target: tgt(WEB) };
// L) REFUSALS the page decides (review finds 2026-09-11): an id no column can hold (a create in flight, a sub-agent viewer)
//    is refused at the one mutation with a line and nothing changes, from the palette too; a column whose last listed
//    member would leave over a create in flight keeps it — from a move, the cross and the palette's close alike — while a
//    column with two members lets one go, and the create resolving frees it; another dashboard tab's write that drops it is
//    deferred, not refused (P below)
boot({}, false);
window.__rompMoveTab(API, 'new');
const PROV = 'new-abc123', VIEWER = WEB + '/agent/a1';
UNMOVABLE.add(PROV); UNMOVABLE.add(VIEWER);
CALLS.notify = []; CALLS.sets = []; CALLS.taken = []; CALLS.splitGrow = [];
out.unmovable = { prov: window.__rompMoveTab(PROV, 'new'), provInto2: window.__rompMoveTab(PROV, 2), viewer: window.__rompMoveTab(VIEWER, 'new'),
                  notify: CALLS.notify.slice(), stored: cols(), ids: ids(), saves: saves(), taken: CALLS.taken.slice(), grown: CALLS.splitGrow.slice() };
BYID['f-chat']._active = PROV; CALLS.notify = [];
out.unmovable.palette = { r: window.__rompSplitChat(), notify: CALLS.notify.slice(), stored: cols(), ids: ids() };
BYID['f-chat']._active = '';
// the tab lock (T395 round one): the page answers 'locked', and the toast names the gear's menu (T405), not "an open session"
LOCKED_SIDS.add(API); CALLS.notify = [];
out.locked = { r: window.__rompMoveTab(API, 2), notify: CALLS.notify.slice(), stored: cols(), ids: ids() };
LOCKED_SIDS = new Set();
// an OLDER chat bundle (no __rompMoveRefusal on its frame): the shell falls to the movable question and its one line (round two, LOW 3)
const olderWin = BYID['f-chat'].contentWindow, refusalFn = olderWin.__rompMoveRefusal;
delete olderWin.__rompMoveRefusal; UNMOVABLE.add(PROV); CALLS.notify = [];
out.older = { r: window.__rompMoveTab(PROV, 'new'), notify: CALLS.notify.slice(), hasField: typeof olderWin.__rompMoveRefusal };
olderWin.__rompMoveRefusal = refusalFn; UNMOVABLE = new Set();
BUSY['f-chat-2'] = true; CALLS.notify = []; CALLS.sets = []; CALLS.taken = []; CALLS.unregister = [];
out.busy = { home: window.__rompMoveTab(API, 1), ids: ids(), stored: cols(), notify: CALLS.notify.slice(), saves: saves(), taken: CALLS.taken.slice() };
crossOf('f-chat-2').fire('click', { stopPropagation() {} });
out.busy.cross = { ids: ids(), stored: cols(), notify: CALLS.notify.slice(), unregister: CALLS.unregister.slice(), taken: CALLS.taken.slice() };
window.__rompCloseSplit(2);
out.busy.palette = { ids: ids(), notify: CALLS.notify.length };
window.__rompMoveTab(TESTS, 2); CALLS.notify = [];
out.busy.twoMembers = { home: (window.__rompMoveTab(TESTS, 1) || {}).id, stored: cols(), notify: CALLS.notify.slice(), ids: ids() };
BUSY['f-chat-2'] = false; CALLS.notify = [];
out.busy.thenFree = { home: (window.__rompMoveTab(API, 1) || {}).id, ids: ids(), stored: cols(), notify: CALLS.notify.slice() };
boot({ 'romp-chat-cols': JSON.stringify({ v: 2, cols: [{ n: 2, ids: [WEB] }] }) }, false);
BUSY['f-chat-2'] = true; STORE['romp-chat-cols'] = JSON.stringify({ v: 2, cols: [] }); CALLS.notify = [];
window.dispatchEvent({ type: 'storage', key: 'romp-chat-cols' });
out.busy.reconciled = { ids: ids(), notify: CALLS.notify.slice(), saves: saves() };
// M) a colEmpty that closes a column tells the first column which of its gone ids the page's own cross removed (crossed),
//    ahead of the store write; a prune that leaves members says nothing; a gone id nobody crossed is not held (it is the
//    first column's the moment its strip repaints); a crossed id the entry did not hold is ignored
boot({}, false);
window.__rompMoveTab(API, 'new'); window.__rompMoveTab(TESTS, 2);
CALLS.posted = []; SEQ = [];
msg({ romp: 'colEmpty', gone: [TESTS], crossed: [TESTS] }, 'f-chat-2');
out.closing = { partial: CALLS.posted.slice() };
CALLS.posted = []; SEQ = [];
msg({ romp: 'colEmpty', gone: [API, X], crossed: [API, X] }, 'f-chat-2');
out.closing.all = { posted: CALLS.posted.slice(), seq: SEQ.filter((x) => x.indexOf('post:') === 0 || x === 'set:romp-chat-cols'), ids: ids(), stored: cols() };
boot({}, false);
window.__rompMoveTab(API, 'new');
CALLS.posted = [];
msg({ romp: 'colEmpty', gone: [API] }, 'f-chat-2');   // no cross named (a page misled by a stale frame, an older page): the column closes, nothing is held
out.closing.uncrossed = { posted: CALLS.posted.filter((p) => p.m && p.m.romp === 'closing'), ids: ids(), stored: cols() };
boot({}, false);
window.__rompMoveTab(API, 'new');
CALLS.posted = [];
msg({ romp: 'colEmpty', gone: [API], crossed: [] }, 'f-chat-2');
out.closing.emptyCross = { posted: CALLS.posted.filter((p) => p.m && p.m.romp === 'closing'), ids: ids(), stored: cols() };
// N) ORPHANED STATE: a page's offer of state for sessions it does not show is taken from it and handed to the owner's page
//    when that page can hear it; its own member and junk are skipped; a target not yet evaluated leaves the state where it is
boot({ 'romp-chat-cols': '[2]', 'romp-vscode-state-chat:2': JSON.stringify({ activeId: WEB, drafts: { [WEB]: 'a', [API]: 'b' } }) }, false);
window.__rompMoveTab(TESTS, 'new');   // column 3 holds TESTS
TAKE['f-chat-2'] = { [API]: { draft: 'b', citations: [], files: [], staged: [] }, [TESTS]: { draft: 't', citations: [], files: [], staged: [] }, [WEB]: { draft: 'a', citations: [], files: [], staged: [] } };
CALLS.posted = []; CALLS.taken = [];
msg({ romp: 'orphanState', sids: [API, TESTS, WEB, '', 7] }, 'f-chat-2');
out.orphan = { posted: CALLS.posted.slice(), taken: CALLS.taken.slice(), left: Object.keys(TAKE['f-chat-2']), stored: cols() };
delete BYID['f-chat'].contentWindow.__rompTakeSessionState;   // the first column's bundle has not evaluated: it cannot hear an adopt
TAKE['f-chat-2'] = { [API]: { draft: 'b', citations: [], files: [], staged: [] } };
CALLS.posted = []; CALLS.taken = [];
msg({ romp: 'orphanState', sids: [API] }, 'f-chat-2');
out.orphan.unloaded = { posted: CALLS.posted.slice(), taken: CALLS.taken.slice(), left: Object.keys(TAKE['f-chat-2']) };
msg({ romp: 'orphanState', sids: [API] });   // from no chat column: nothing
out.orphan.unknown = CALLS.posted.length;
// O) a closing column's width goes to the column on its left, measured before its key is dropped
boot({}, false);
window.__rompMoveTab(API, 'new'); window.__rompMoveTab(TESTS, 'new');
CALLS.splitShrink = []; CALLS.unregister = []; SEQ = [];
window.__rompCloseSplit(3);
out.shrink = { third: CALLS.splitShrink.slice(), unregister: CALLS.unregister.slice(), seq: SEQ.filter((x) => x.indexOf('set:') !== 0) };
CALLS.splitShrink = [];
window.__rompCloseSplit(2);
out.shrink.second = CALLS.splitShrink.slice();
// P) a peer dashboard's write that drops a BUSY column is DEFERRED: the reconcile's close passed `keep`, which skips close()'s
//    busy gate, so it tore the column down over a create in flight and the queued text died with the document. The column,
//    its entry and every reader stand and nothing is written back; the page's idle signal closes it against a fresh read of
//    the store, so a column the peer listed again meanwhile stays; a column that is not busy still closes at once
boot({ 'romp-chat-cols': JSON.stringify({ v: 2, cols: [{ n: 2, ids: [WEB] }, { n: 3, ids: [API] }] }) }, false);
BUSY['f-chat-2'] = true; CALLS.sets = []; CALLS.posted = []; CALLS.taken = []; CALLS.unregister = []; CALLS.notify = [];
STORE['romp-chat-cols'] = JSON.stringify({ v: 2, cols: [{ n: 3, ids: [API] }] });
window.dispatchEvent({ type: 'storage', key: 'romp-chat-cols' });
out.deferred = { ids: ids(), order: order(), sets: window.__rompChatSets(), saves: saves(), unregister: CALLS.unregister.slice(), notify: CALLS.notify.slice(), targetWeb: tgt(WEB) };
msg({ romp: 'colBusy', busy: true }, 'f-chat-2');    // not idle yet: nothing
msg({ romp: 'colBusy', busy: false }, 'f-chat-3');   // an idle signal from a column nobody deferred: nothing
out.deferred.notYet = { ids: ids(), saves: saves(), unregister: CALLS.unregister.slice() };
BUSY['f-chat-2'] = false; TAKE['f-chat-2'] = { [WEB]: { draft: 'typed while it started', citations: [], files: [], staged: [] } };
msg({ romp: 'colBusy', busy: false }, 'f-chat-2');
out.deferred.idle = { ids: ids(), sets: window.__rompChatSets(), saves: saves(), unregister: CALLS.unregister.slice(), posted: CALLS.posted.slice(), taken: CALLS.taken.slice(),
                      targetWeb: tgt(WEB), notify: CALLS.notify.slice(), stored: cols() };
// the peer lists the column again before the page is idle: unheard (the fresh read finds it) and heard (the entry is the peer's again)
boot({ 'romp-chat-cols': JSON.stringify({ v: 2, cols: [{ n: 2, ids: [WEB] }] }) }, false);
BUSY['f-chat-2'] = true; CALLS.sets = []; CALLS.unregister = [];
STORE['romp-chat-cols'] = JSON.stringify({ v: 2, cols: [] });
window.dispatchEvent({ type: 'storage', key: 'romp-chat-cols' });
STORE['romp-chat-cols'] = JSON.stringify({ v: 2, cols: [{ n: 2, ids: [WEB] }] });
BUSY['f-chat-2'] = false;
msg({ romp: 'colBusy', busy: false }, 'f-chat-2');
out.deferred.relisted = { ids: ids(), sets: window.__rompChatSets(), saves: saves(), unregister: CALLS.unregister.slice() };
BUSY['f-chat-2'] = true;
STORE['romp-chat-cols'] = JSON.stringify({ v: 2, cols: [] });
window.dispatchEvent({ type: 'storage', key: 'romp-chat-cols' });
STORE['romp-chat-cols'] = JSON.stringify({ v: 2, cols: [{ n: 2, ids: [WEB, TESTS] }] });
window.dispatchEvent({ type: 'storage', key: 'romp-chat-cols' });
out.deferred.relistedHeard = { ids: ids(), sets: window.__rompChatSets(), saves: saves(), unregister: CALLS.unregister.slice() };
BUSY['f-chat-2'] = false;
msg({ romp: 'colBusy', busy: false }, 'f-chat-2');
out.deferred.relistedHeard.thenIdle = { ids: ids(), sets: window.__rompChatSets(), saves: saves() };
STORE['romp-chat-cols'] = JSON.stringify({ v: 2, cols: [] });
window.dispatchEvent({ type: 'storage', key: 'romp-chat-cols' });
out.deferred.notBusy = { ids: ids(), saves: saves(), unregister: CALLS.unregister.slice() };
// the create RESOLVES in the deferred column: the page claims the real id for it (adoptProvisional, ahead of the drop), which
// writes the column back into the store, so the idle signal that follows keeps it
boot({ 'romp-chat-cols': JSON.stringify({ v: 2, cols: [{ n: 2, ids: [WEB] }] }) }, false);
BUSY['f-chat-2'] = true; CALLS.sets = [];
STORE['romp-chat-cols'] = JSON.stringify({ v: 2, cols: [] });
window.dispatchEvent({ type: 'storage', key: 'romp-chat-cols' });
const claimed = window.__rompClaimSession(X, 2);
BUSY['f-chat-2'] = false;
msg({ romp: 'colBusy', busy: false }, 'f-chat-2');
out.deferred.created = { claimed, ids: ids(), sets: window.__rompChatSets(), stored: cols(), saves: saves() };
// Q) a peer write that drops a PARENT column whose BOTTOM pane is BUSY defers the WHOLE column (MEDIUM 2): reconcile
//    reaches the parent first, not busy, and a plain close(keep) would skip the kid's busy gate and tear the busy bottom
//    iframe down; instead the parent is deferred because its nested pane is busy, and the kid's idle signal closes it
boot({ 'romp-chat-cols': JSON.stringify({ v: 2, cols: [{ n: 2, ids: [WEB] }, { n: 3, ids: [API], place: 'below', parent: 2, ratio: 0.5 }] }) }, false);
BUSY['f-chat-2'] = false; BUSY['f-chat-3'] = true; CALLS.notify = [];
STORE['romp-chat-cols'] = JSON.stringify({ v: 2, cols: [] });
window.dispatchEvent({ type: 'storage', key: 'romp-chat-cols' });
out.kidBusy = { ids: ids(), stored: cols() };
BUSY['f-chat-3'] = false;
msg({ romp: 'colBusy', busy: false }, 'f-chat-3');   // the bottom pane's idle clears the PARENT's deferral and the column closes
out.kidBusy.afterIdle = { ids: ids(), stored: cols() };
// R) round four LOW 3: close() clears the KID's deferral too. A deferred parent+kid pair closed by hand must not leave
//    deferred[kid.n], else when the kid's NUMBER is reused its ordinary idle fires an unasked reconcile that applies an
//    unheard peer write and tears a live column down.
boot({ 'romp-chat-cols': JSON.stringify({ v: 2, cols: [{ n: 2, ids: [WEB] }, { n: 3, ids: [API], place: 'below', parent: 2, ratio: 0.5 }] }) }, false);
BUSY['f-chat-2'] = true; BUSY['f-chat-3'] = true;
STORE['romp-chat-cols'] = JSON.stringify({ v: 2, cols: [] });
window.dispatchEvent({ type: 'storage', key: 'romp-chat-cols' });   // reconcile defers BOTH 2 (busy kid) and 3 (busy), keeps them
BUSY['f-chat-2'] = false; BUSY['f-chat-3'] = false;
window.__rompCloseSplit(2);   // by-hand close of the deferred parent + its kid
window.__rompMoveTab(WEB, 'new'); window.__rompMoveTab(API, 'new');   // numbers 2 then 3 reused (f-chat-3 exists again)
STORE['romp-chat-cols'] = JSON.stringify({ v: 2, cols: [{ n: 3, ids: [API] }] });   // a peer dropped col 2; a stale deferred[3] idle would reconcile to this and close col 2
msg({ romp: 'colBusy', busy: false }, 'f-chat-3');   // the reused f-chat-3's ordinary idle: with deferred[3] cleared by close(), a no-op
out.kidStale = { ids: ids(), stored: cols() };
// S) round four LOW 5: an orphan below entry (parent gone from the store) is DROPPED at read(), not degraded to a
//    paneless side column: make()'s frame-exists guard skips it (the busy kid's iframe survives), so a degraded side
//    entry would leave lastPane() naming a chat-pane-<n> that was never created.
boot({ 'romp-chat-cols': JSON.stringify({ v: 2, cols: [{ n: 2, ids: [WEB] }, { n: 3, ids: [API], place: 'below', parent: 2, ratio: 0.5 }] }) }, false);
BUSY['f-chat-3'] = true;
STORE['romp-chat-cols'] = JSON.stringify({ v: 2, cols: [{ n: 3, ids: [API], place: 'below', parent: 2, ratio: 0.5 }] });   // a peer dropped col 2, orphaning the below entry 3
window.dispatchEvent({ type: 'storage', key: 'romp-chat-cols' });
out.orphanKept = { lastPane: window.__rompLastChatPane(), lastPaneExists: !!document.getElementById(window.__rompLastChatPane()), stored: cols() };
// T) round four LOW 2: the persisted gutter ratio is the exact on-screen fraction even on a tall (>1600px) pane; a fixed
//    0.05 fraction clamp would drift from mv()'s pixel minimum (mn=min(80,sum*0.2)=80 at sum=2000).
boot({ 'romp-chat-cols': JSON.stringify({ v: 2, cols: [{ n: 2, ids: [WEB] }, { n: 3, ids: [API], place: 'below', parent: 2, ratio: 0.5 }] }) }, false);
document.getElementById('f-chat-2')._rect.height = 1000; document.getElementById('chat-sub-3')._rect.height = 1000;   // sum = 2000
document.getElementById('gh-chat-3').fire('mousedown', { clientY: 1000, preventDefault() {} });
window.dispatchEvent({ type: 'mousemove', clientY: 0 });   // drag the gutter fully up: mv() clamps the top to mn=80px
window.dispatchEvent({ type: 'mouseup' });
out.ratioDrift = { ratio: (cols().cols.find((c) => c.place === 'below') || {}).ratio, topFlex: document.getElementById('f-chat-2').style.flex };
console.log(JSON.stringify(out));
"""


class SplitExecutes(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        script = HARNESS.replace("__SPLIT_JS__", json.dumps(km._LANDING_SPLIT_JS)) + DRIVER
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(script)
            path = f.name
        try:
            r = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        finally:
            os.unlink(path)
        assert r.returncode == 0, "the split's JS threw: " + r.stderr[:1200]
        cls.out = json.loads(r.stdout.strip().splitlines()[-1])

    def test_a_fresh_dashboard_has_one_column_that_holds_everything(self):
        o = self.out["fresh"]
        self.assertEqual(o["ids"], ["f-chat"])
        self.assertEqual(o["order"], ["chat-pane", "gv-a", "fleet-pane", "gv-b", "feed-pane"])
        self.assertEqual(o["lastPane"], "chat-pane")
        self.assertEqual(o["sets"], {}, "no later columns: the pages filter nothing")
        self.assertIsNone(o["stored"], "nothing written until something changes")
        self.assertEqual(o["saves"], 0)
        self.assertEqual(o["targetUnknown"], "f-chat", "a session no entry lists is the first column's")
        self.assertEqual(o["targetNone"], "f-chat", "no session named: the column last worked in, here the first")

    def test_a_v1_store_migrates_once_to_the_sessions_the_blobs_named(self):
        m = self.out["migrated"]
        self.assertEqual(m["ids"], ["f-chat", "f-chat-2"])
        self.assertEqual(m["stored"], {"v": 2, "cols": [{"n": 2, "ids": [WEB]}]}, "written back in the new shape")
        self.assertEqual(m["saves"], 1, "…once")
        self.assertEqual(m["sets"], {"2": [WEB]})
        self.assertEqual(m["blob2"], {"activeId": WEB, "scroll": 4}, "the blob is re-seeded with the same tab: every other field kept")
        self.assertEqual(m["posted"], [], "no focus, no adopt: the blob names the tab")
        self.assertEqual(m["srcs"], ["/chat?col=2&skeleton=1"])
        d = self.out["migratedDrop"]
        self.assertEqual(d["ids"], ["f-chat", "f-chat-2"], "a number whose blob names no session is dropped")
        self.assertEqual(d["stored"], {"v": 2, "cols": [{"n": 2, "ids": [WEB]}]})

    def test_a_move_to_a_new_column_makes_a_wired_column_holding_the_session_alone(self):
        o = self.out["moved"]
        self.assertEqual(o["id"], "f-chat-2")
        self.assertEqual(o["src"], "/chat?col=2&skeleton=1", "its own state blob + connect params (the shim); a skeleton client of its session")
        self.assertEqual(o["col"], "2")
        self.assertEqual(o["pane"], "chat-pane-2")
        self.assertEqual(o["paneCls"], "pane chat-col")
        self.assertEqual(o["flex"], "var(--g-chat2,60) 1 0", "its own grow var, the gutters' store")
        self.assertEqual(o["order"], ["chat-pane", "gv-chat-2", "chat-pane-2", "gv-a", "fleet-pane", "gv-b", "feed-pane"])
        self.assertEqual(o["stored"], {"v": 2, "cols": [{"n": 2, "ids": [API]}]})
        self.assertEqual(o["sets"], {"2": [API]}, "what every column page filters by")
        self.assertEqual(o["blob2"], {"activeId": API}, "the blob names the session BEFORE the frame exists: the shim's hint, the page's wantActive")
        self.assertEqual(o["splitGrow"], [["chat-pane", "chat2"]], "the rightmost column and the new one each take half its width")
        self.assertEqual(o["growFair"], ["chat2"], "then the store-aware hook finds the half and keeps it")
        self.assertEqual(o["register"], [["chat-pane-2", "chat2"]])
        self.assertEqual(o["wireFocus"], ["f-chat-2"])
        self.assertEqual(o["wireEsc"], ["f-chat-2"])
        self.assertEqual(o["gutter"], [{"gid": "gv-chat-2", "left": "chat-pane", "right": "chat-pane-2"}])
        self.assertEqual(o["event"], [{"col": 2, "open": True, "frame": "f-chat-2"}], "palette-main wires its chords on this")
        self.assertEqual(o["posted"], [], "no hand-over focus and, with nothing held for the session, no adopt — though load fired twice")
        self.assertEqual(o["taken"], [["f-chat", API, False]], "the source page was asked for the session's drafts, once")
        self.assertEqual(o["focused"], ["f-chat-2"], "the new column takes the keyboard")
        self.assertEqual(o["crossTitle"], "Close this column")
        self.assertEqual(o["targetApi"], "f-chat-2", "a focus for the session belongs to the column holding it")
        self.assertEqual(o["targetTests"], "f-chat", "…and one for a session no entry lists to the first column")
        self.assertTrue(o["canSplit"])
        self.assertEqual(o["ids"], ["f-chat", "f-chat-2"])
        self.assertEqual(o["lastPane"], "chat-pane-2", "gv-a's left neighbour is now the new column")
        self.assertEqual(o["paneOf"], "chat-pane-2")
        self.assertEqual(o["colOf"], "2")
        self.assertTrue(o["frameOfWin"])

    def test_a_move_between_columns_lands_in_the_target_and_closes_an_emptied_origin(self):
        t = self.out["third"]
        self.assertEqual(t["id"], "f-chat-3")
        self.assertEqual(t["splitGrow"], [["chat-pane", "chat2"], ["chat-pane-2", "chat3"]], "the second new column halves the RIGHTMOST column")
        self.assertEqual(t["stored"], {"v": 2, "cols": [{"n": 2, "ids": [API]}, {"n": 3, "ids": [TESTS]}]})
        self.assertEqual(t["gutterLeft3"], "chat-pane-2")
        m = self.out["movedInto3"]
        self.assertEqual(m["target"], "f-chat-3", "the target's iframe comes back")
        self.assertEqual(m["ids"], ["f-chat", "f-chat-3"], "column 2 held only the moved session: it closed")
        self.assertEqual(m["order"], ["chat-pane", "gv-chat-3", "chat-pane-3", "gv-a", "fleet-pane", "gv-b", "feed-pane"])
        self.assertEqual(m["stored"], {"v": 2, "cols": [{"n": 3, "ids": [TESTS, API]}]}, "the id joins the target's entry; the emptied entry is gone whole")
        self.assertEqual(m["sets"], {"3": [TESTS, API]})
        self.assertEqual(m["posted"], [{"id": "f-chat-3", "m": {"type": "focus", "id": API}}], "a plain focus into the target: it is the owner now, so its own gate takes it; no `own`")
        self.assertEqual(m["taken"], [["f-chat-2", API, False]], "the drafts were asked of the SOURCE column")
        self.assertEqual(m["unregister"], ["chat-pane-2"], "the closed column's grow leaves the store")
        self.assertEqual(m["colGone"], ["2"], "the Log drops its connection state")
        self.assertEqual(m["closedEvent"], [2])
        self.assertEqual(m["focused"][-1], "f-chat-3", "the ring ends on the target, not on the closed origin's neighbour")
        self.assertEqual(m["targetApi"], "f-chat-3")
        self.assertEqual(m["targetTests"], "f-chat-3")
        self.assertEqual(m["targetWeb"], "f-chat")
        self.assertEqual(m["stale"], "f-chat", "a stale focus id falls back to the first column")
        self.assertEqual(m["focusedNone"], "f-chat-3", "no session named: the column last worked in")
        h = self.out["movedHome"]
        self.assertEqual(h["target"], "f-chat", "the first column derives: the id simply leaves its entry")
        self.assertEqual(h["ids"], ["f-chat", "f-chat-3"], "the origin keeps its other member")
        self.assertEqual(h["stored"], {"v": 2, "cols": [{"n": 3, "ids": [TESTS]}]})
        self.assertEqual(h["sets"], {"3": [TESTS]})
        self.assertEqual(h["posted"], [{"id": "f-chat", "m": {"type": "focus", "id": API}}])
        self.assertEqual(h["focused"], ["f-chat"])
        self.assertEqual(h["targetApi"], "f-chat")

    def test_a_refused_move_says_why_or_changes_nothing(self):
        r = self.out["refused"]
        self.assertIsNone(r["alone"], "a session alone in a later column has nowhere new to go")
        self.assertIsNone(r["noSuch"], "no such column")
        self.assertIsNone(r["noSid"])
        self.assertEqual(r["same"], "f-chat-3", "already there: the owner's frame, nothing moves")
        self.assertEqual(r["sameHome"], "f-chat")
        self.assertEqual(r["notify"], [["warn", "This session is already alone in its column."]], "the one refusal that is a gesture with nothing to do says so")
        self.assertEqual(r["stored"], {"v": 2, "cols": [{"n": 3, "ids": [TESTS]}]}, "the store is untouched")
        self.assertEqual(r["posted"], 0)
        self.assertEqual(r["saves"], 0, "no write for a refusal or a no-op")
        p = self.out["paletteNone"]
        self.assertIsNone(p["r"])
        self.assertEqual(p["notify"], [["warn", "No session is open in this column to move."]])
        q = self.out["paletteMove"]
        self.assertEqual(q["id"], "f-chat-2", "the focused column's active tab moves to a new column, the lowest free number")
        self.assertEqual(q["stored"], {"v": 2, "cols": [{"n": 3, "ids": [TESTS]}, {"n": 2, "ids": [WEB]}]}, "row order, not number order")
        self.assertEqual(q["notify"], [])
        self.assertEqual(q["toggle"], [["chat", True]], "a hidden chat group is brought forward first")
        self.assertEqual(q["blob2"], {"activeId": WEB})

    def test_a_column_s_emptiness_prunes_its_entry_and_closes_it_only_when_nothing_is_left(self):
        p = self.out["colEmptyPartial"]
        self.assertEqual(p["ids"], ["f-chat", "f-chat-2"])
        self.assertEqual(p["stored"], {"v": 2, "cols": [{"n": 2, "ids": [API]}]}, "the gone id leaves the entry")
        self.assertEqual(p["saves"], 1)
        self.assertEqual(self.out["colEmptyIgnored"]["stored"], {"v": 2, "cols": [{"n": 2, "ids": [API]}]}, "a page with no entry says nothing that changes anything")
        k = self.out["colEmptyKept"]
        self.assertEqual(k["ids"], ["f-chat", "f-chat-2"], "a member added meanwhile keeps the column open")
        self.assertEqual(k["stored"], {"v": 2, "cols": [{"n": 2, "ids": [X]}]})
        a = self.out["colEmptyAll"]
        self.assertEqual(a["ids"], ["f-chat"], "the last member gone: the column closes")
        self.assertEqual(a["stored"], {"v": 2, "cols": []})
        self.assertEqual(a["unregister"], ["chat-pane-2"])

    def test_another_dashboard_tab_s_write_is_reconciled_without_writing_back(self):
        r = self.out["reconciled"]
        self.assertEqual(r["ids"], ["f-chat", "f-chat-2", "f-chat-4"], "the column the other tab added is made here")
        self.assertEqual(r["order"][:5], ["chat-pane", "gv-chat-2", "chat-pane-2", "gv-chat-4", "chat-pane-4"])
        self.assertEqual(r["sets"], {"2": [WEB], "4": [API, TESTS]})
        self.assertEqual(r["saves"], 0, "the other tab's store is the truth: nothing is written back")
        self.assertEqual(r["blob4"], {"activeId": TESTS, "scroll": 9}, "seeded like a restore: the blob's tab, a member, stands")
        self.assertEqual(r["posted"], [])
        c = self.out["reconciledClose"]
        self.assertEqual(c["ids"], ["f-chat", "f-chat-4"], "the column the other tab dropped closes here")
        self.assertEqual(c["sets"], {"4": [API, TESTS]})
        self.assertEqual(c["saves"], 0)
        self.assertEqual(c["unregister"], ["chat-pane-2"])
        self.assertEqual(self.out["reconciledOther"]["ids"], ["f-chat", "f-chat-4"], "another key's event changes nothing")

    def test_the_cross_returns_the_column_s_sessions_to_the_first_column_with_their_drafts(self):
        c = self.out["cross"]
        self.assertEqual(c["ids"], ["f-chat"])
        self.assertEqual(c["stored"], {"v": 2, "cols": []}, "the entry goes whole: the first column derives both sessions")
        self.assertEqual(c["sets"], {})
        self.assertEqual(c["taken"], [["f-chat-2", API, True], ["f-chat-2", TESTS, False]], "the closing page is asked for each member's drafts")
        self.assertEqual(c["posted"], [{"id": "f-chat", "m": {"romp": "adopt", "sid": API, "state": {"draft": "a draft for api", "citations": [], "files": [], "staged": []}}}],
                         "what it held lands in the first column's page; a session with nothing held posts nothing")
        self.assertEqual(c["targetApi"], "f-chat")
        self.assertEqual(c["targetTests"], "f-chat")

    def test_drafts_travel_with_a_moved_tab(self):
        n = self.out["draftsNew"]
        self.assertEqual(n["id"], "f-chat-2")
        self.assertEqual(n["taken"], [["f-chat", TESTS, True]], "taken from the source, synchronously, before the frame exists")
        self.assertEqual(n["postedBeforeLoad"], [], "a new frame cannot hear yet")
        self.assertEqual(n["postedAfterLoad"], [{"id": "f-chat-2", "m": {"romp": "adopt", "sid": TESTS,
                                                  "state": {"draft": "typed in column one", "citations": [{"title": "a card"}], "files": ["/tmp/a.png"], "staged": []}}}],
                         "…and adopts on its load")
        self.assertEqual(n["postedAfterSecondLoad"], 1, "once: a later reload of the frame has them in its own blob")
        o = self.out["draftsOpen"]
        self.assertEqual(o["target"], "f-chat-3")
        self.assertEqual(o["taken"], [["f-chat-2", TESTS, True]])
        self.assertEqual(o["posted"], [{"id": "f-chat-3", "m": {"romp": "adopt", "sid": TESTS, "state": {"draft": "more", "citations": [], "files": [], "staged": [{"text": "s", "cites": []}]}}},
                                       {"id": "f-chat-3", "m": {"type": "focus", "id": TESTS}}], "an open column adopts at once, ahead of the focus that shows the tab")
        self.assertEqual(o["ids"], ["f-chat", "f-chat-3"], "the origin, left empty, closed")
        self.assertEqual(o["stored"], {"v": 2, "cols": [{"n": 3, "ids": [WEB, TESTS]}]})

    def test_a_created_session_is_claimed_for_its_column_once_and_never_stolen(self):
        c = self.out["claim"]
        self.assertTrue(c["first"], "a session no entry lists joins the creating column")
        self.assertFalse(c["again"], "…once")
        self.assertFalse(c["steal"], "a session another column lists is never taken")
        self.assertFalse(c["listed"])
        self.assertFalse(c["noSid"])
        self.assertFalse(c["noCol"])
        self.assertEqual(c["stored"], {"v": 2, "cols": [{"n": 2, "ids": [API, X]}, {"n": 3, "ids": [WEB]}]})
        self.assertEqual(c["targetX"], "f-chat-2")

    def test_the_restore_seeds_each_column_with_a_member_and_reads_a_bad_store_forgivingly(self):
        r = self.out["restored"]
        self.assertEqual(r["ids"], ["f-chat", "f-chat-2", "f-chat-5"])
        self.assertEqual(r["order"][:5], ["chat-pane", "gv-chat-2", "chat-pane-2", "gv-chat-5", "chat-pane-5"])
        self.assertEqual(r["blob2"], {"activeId": API, "scroll": 3}, "the blob's tab is still a member: it stands, every other field kept")
        self.assertEqual(r["blob5"], {"activeId": TESTS}, "no blob: seeded with the first member")
        self.assertEqual(r["srcs"], ["/chat?col=2&skeleton=1", "/chat?col=5&skeleton=1"], "a restored column dials as a skeleton client of the seeded tab")
        self.assertEqual(r["posted"], [], "no focus, no adopt at a restore")
        self.assertEqual(r["sets"], {"2": [WEB, API], "5": [TESTS]})
        self.assertEqual(r["saves"], 0, "a v2 store is not rewritten at boot")
        self.assertEqual(r["growFair"], ["chat2", "chat5"], "a restored column takes its stored width, else the fair average")
        self.assertEqual(r["splitGrow"], [], "…never the halving, which is a move's")
        self.assertEqual(r["lastPane"], "chat-pane-5")
        self.assertEqual(r["nextNumber"], "f-chat-3", "a new column takes the lowest free number")
        self.assertEqual(self.out["restoredMovedAway"]["blob2"], {"activeId": WEB}, "the blob's tab was moved away while the browser was closed: the first member")
        self.assertEqual(self.out["corrupt"]["ids"], ["f-chat"], "a corrupt store makes nothing and throws nothing")
        s = self.out["sanitised"]
        self.assertEqual(s["ids"], ["f-chat", "f-chat-3"], "an empty entry, a non-numeric number and an entry whose ids were all claimed earlier are dropped")
        self.assertEqual(s["sets"], {"3": [API]}, "an id is in one entry, once")

    def test_four_columns_at_most(self):
        c = self.out["cap"]
        self.assertEqual(c["ids"], ["f-chat", "f-chat-2", "f-chat-3", "f-chat-4"])
        self.assertIsNone(c["fourth"])
        self.assertEqual(c["notify"], [["warn", "Four panes at most, close one first."]], "a refused move says why")
        self.assertFalse(c["canSplit"], "…and the tab menu can ask before offering the item")
        self.assertEqual(c["stored"], {"v": 2, "cols": [{"n": 2, "ids": [WEB]}, {"n": 3, "ids": [API]}, {"n": 4, "ids": [TESTS]}]})

    def test_an_id_no_column_can_hold_is_refused_at_the_one_mutation_with_a_line(self):
        # a create in flight and a sub-agent viewer carry data-id on the strip, and the palette's DOM read can name them
        # (review find 2026-09-11: a column opened on a provisional id the kernel does not know flashed open and shut)
        u = self.out["unmovable"]
        self.assertIsNone(u["prov"]); self.assertIsNone(u["provInto2"]); self.assertIsNone(u["viewer"])
        self.assertEqual(u["notify"], [["warn", "Only an open session can be moved between columns."]] * 3, "each refusal says why")
        self.assertEqual(u["stored"], {"v": 2, "cols": [{"n": 2, "ids": [API]}]}, "the store is untouched")
        self.assertEqual(u["ids"], ["f-chat", "f-chat-2"], "no column opened")
        self.assertEqual(u["saves"], 0); self.assertEqual(u["grown"], [], "nothing halved")
        self.assertEqual(u["taken"], [], "no page was asked for drafts: refused before the hand-off")
        p = u["palette"]
        self.assertIsNone(p["r"], "the palette's move of a create in flight (the active tab) is the same refusal")
        self.assertEqual(p["notify"], [["warn", "Only an open session can be moved between columns."]])
        self.assertEqual(p["stored"], u["stored"]); self.assertEqual(p["ids"], ["f-chat", "f-chat-2"])

    def test_a_locked_page_refuses_the_move_with_a_toast_that_names_the_gears_menu(self):
        # T395 round one (MEDIUM 2): the page's answer carries its reason; a lock is not "not an open session", and the toast
        # says the way back
        l = self.out["locked"]
        self.assertIsNone(l["r"])
        self.assertEqual(l["notify"], [["warn", "The tabs are locked: unlock them in the settings (Chat, Tab strip) to move this session."]])   # T415: the lock is a switch in the settings
        self.assertEqual(l["stored"], self.out["unmovable"]["stored"], "the store is untouched")
        self.assertEqual(l["ids"], self.out["unmovable"]["ids"], "no column opened")

    def test_an_older_bundle_without_the_refusal_field_falls_to_the_movable_question(self):
        # round two, LOW 3: a chat page from before the refusal field answers only the movable question, and the shell's one line stands
        o = self.out["older"]
        self.assertEqual(o["hasField"], "undefined", "the frame was minted without the field")
        self.assertIsNone(o["r"])
        self.assertEqual(o["notify"], [["warn", "Only an open session can be moved between columns."]])

    def test_a_column_with_a_create_in_flight_keeps_its_last_member_and_stays_open(self):
        # its queued text and draft would die with the document (review find 2026-09-11): the move that would empty it,
        # its cross and the palette's close are refused with the line; a column with two members lets one go; the create
        # resolving frees it; another dashboard tab's write that drops it is deferred, not refused (the test below)
        b = self.out["busy"]
        self.assertIsNone(b["home"], "the move that would empty the column is refused")
        self.assertEqual(b["notify"], [["warn", "A session is still being created in this column."]])
        self.assertEqual(b["ids"], ["f-chat", "f-chat-2"]); self.assertEqual(b["stored"], {"v": 2, "cols": [{"n": 2, "ids": [API]}]})
        self.assertEqual(b["saves"], 0); self.assertEqual(b["taken"], [], "nothing was taken from the page: refused before the hand-off")
        c = b["cross"]
        self.assertEqual(c["ids"], ["f-chat", "f-chat-2"], "the cross is refused too: the column would die with the create")
        self.assertEqual(c["notify"], [["warn", "A session is still being created in this column."]] * 2)
        self.assertEqual(c["unregister"], []); self.assertEqual(c["taken"], [])
        self.assertEqual(b["palette"], {"ids": ["f-chat", "f-chat-2"], "notify": 3}, "…and the palette's close")
        t = b["twoMembers"]
        self.assertEqual(t["home"], "f-chat", "with two members one may leave: the column stays")
        self.assertEqual(t["stored"], {"v": 2, "cols": [{"n": 2, "ids": [API]}]}); self.assertEqual(t["notify"], []); self.assertEqual(t["ids"], ["f-chat", "f-chat-2"])
        f = b["thenFree"]
        self.assertEqual(f["home"], "f-chat", "the create resolved: the last member leaves and the column closes")
        self.assertEqual(f["ids"], ["f-chat"]); self.assertEqual(f["stored"], {"v": 2, "cols": []}); self.assertEqual(f["notify"], [])
        self.assertEqual(b["reconciled"], {"ids": ["f-chat", "f-chat-2"], "notify": [], "saves": 0},
                         "another dashboard tab's write that drops a busy column is deferred, not carried out under the create, and says nothing")

    def test_a_peer_s_write_that_drops_a_busy_column_is_deferred_until_the_page_is_idle(self):
        # the reconcile's close passed `keep`, which skips close()'s busy gate, so a peer dashboard closing a column tore this
        # tab's column down over a create in flight and its queued text died with the document. Deferred now: the column, its
        # entry and every reader stand, nothing is written back, and the page's idle signal closes it against a fresh read of
        # the store, so a column the peer listed again meanwhile stays; a column that is not busy still closes at once
        d = self.out["deferred"]
        self.assertEqual(d["ids"], ["f-chat", "f-chat-2", "f-chat-3"], "the busy column stands")
        self.assertEqual(d["order"][:5], ["chat-pane", "gv-chat-2", "chat-pane-2", "gv-chat-3", "chat-pane-3"])
        self.assertEqual(d["sets"], {"2": [WEB], "3": [API]}, "its entry stays, at its place: the pages still filter by it")
        self.assertEqual(d["targetWeb"], "f-chat-2", "…and the owner lookup still finds it")
        self.assertEqual(d["saves"], 0, "the peer's store is the truth: nothing is written back"); self.assertEqual(d["unregister"], [])
        self.assertEqual(d["notify"], [], "no toast: nothing was refused")
        n = d["notYet"]
        self.assertEqual(n["ids"], ["f-chat", "f-chat-2", "f-chat-3"], "a busy:true, or an idle signal from a column nobody deferred, changes nothing")
        self.assertEqual(n["saves"], 0); self.assertEqual(n["unregister"], [])
        i = d["idle"]
        self.assertEqual(i["ids"], ["f-chat", "f-chat-3"], "the page's idle signal: the store still lacks the column, so it closes")
        self.assertEqual(i["sets"], {"3": [API]}); self.assertEqual(i["unregister"], ["chat-pane-2"])
        self.assertEqual(i["taken"], [["f-chat-2", WEB, True]])
        self.assertEqual(i["posted"], [{"id": "f-chat", "m": {"romp": "adopt", "sid": WEB, "state": {"draft": "typed while it started", "citations": [], "files": [], "staged": []}}}],
                         "its session returns to the first column, drafts and all")
        self.assertEqual(i["targetWeb"], "f-chat"); self.assertEqual(i["saves"], 0, "still nothing written back"); self.assertEqual(i["notify"], [])
        self.assertEqual(i["stored"], {"v": 2, "cols": [{"n": 3, "ids": [API]}]})
        r = d["relisted"]
        self.assertEqual(r["ids"], ["f-chat", "f-chat-2"], "the peer listed the column again before the idle signal: the fresh read keeps it")
        self.assertEqual(r["sets"], {"2": [WEB]}); self.assertEqual(r["saves"], 0); self.assertEqual(r["unregister"], [])
        h = d["relistedHeard"]
        self.assertEqual(h["ids"], ["f-chat", "f-chat-2"], "…heard as a storage event, the entry is the peer's again and the mark clears")
        self.assertEqual(h["sets"], {"2": [WEB, TESTS]}); self.assertEqual(h["saves"], 0); self.assertEqual(h["unregister"], [])
        self.assertEqual(h["thenIdle"], {"ids": ["f-chat", "f-chat-2"], "sets": {"2": [WEB, TESTS]}, "saves": 0}, "the idle signal then changes nothing")
        self.assertEqual(d["notBusy"], {"ids": ["f-chat"], "saves": 0, "unregister": ["chat-pane-2"]}, "a column that is not busy still closes at once")
        c = d["created"]
        self.assertTrue(c["claimed"], "the create resolved: the page claims the real id for its column, whose entry the deferral kept")
        self.assertEqual(c["stored"], {"v": 2, "cols": [{"n": 2, "ids": [WEB, X]}]}, "the claim writes the column back into the store")
        self.assertEqual(c["saves"], 1)
        self.assertEqual(c["ids"], ["f-chat", "f-chat-2"], "so the idle signal that follows keeps it, with the new session")
        self.assertEqual(c["sets"], {"2": [WEB, X]})

    def test_a_peer_dropping_a_parent_with_a_busy_bottom_pane_defers_the_whole_column(self):
        # MEDIUM 2: reconcile reaches the parent first, not busy, and a plain close(keep) would skip the kid's busy gate,
        # tearing the busy bottom iframe down over its create. A parent whose nested pane is busy is deferred like a busy
        # column, and the bottom pane's idle signal (which clears the PARENT's deferral) then closes it.
        k = self.out["kidBusy"]
        self.assertEqual(k["ids"], ["f-chat", "f-chat-2", "f-chat-3"], "the parent AND its busy bottom pane stand (deferred, frames present), not torn down: %r" % k)
        self.assertEqual(k["afterIdle"]["ids"], ["f-chat"], "the bottom pane's idle signal closes the deferred column and its kid: %r" % k["afterIdle"])

    def test_close_clears_a_deferred_kids_deferral_so_a_reused_number_runs_no_unasked_reconcile(self):
        # round four LOW 3: close() splices the kid out and must delete deferred[kid.n] too, not only deferred[n]. Else,
        # when the kid's NUMBER is reused, that new column's ordinary idle sees a stale deferred mark, fires an unasked
        # reconcile, and applies an unheard peer write (here: dropping the live column 2).
        o = self.out["kidStale"]
        self.assertEqual(o["ids"], ["f-chat", "f-chat-2", "f-chat-3"],
                         "the reused number's idle is a no-op (deferred[kid.n] was cleared by close); column 2 survives. "
                         "A stale mark would reconcile to the peer write and leave only ['f-chat','f-chat-3']: %r" % o)

    def test_an_orphan_below_entry_is_dropped_at_read_not_left_as_a_paneless_side_column(self):
        # round four LOW 5: read() drops an orphan below entry (its parent gone) rather than degrading it to a side column.
        # A degraded side entry whose bottom iframe still exists (a busy kid deferred by reconcile) is skipped by make()'s
        # frame-exists guard, so no chat-pane-<n> is created and lastPane() names a pane that does not exist.
        o = self.out["orphanKept"]
        self.assertEqual(o["lastPane"], "chat-pane-2", "the orphan is dropped, so the last SIDE column is the real column 2: %r" % o)
        self.assertTrue(o["lastPaneExists"], "lastPane() names a .pane that exists (a degraded orphan would name a missing chat-pane-3): %r" % o)

    def test_the_persisted_gutter_ratio_is_the_on_screen_fraction_even_on_a_tall_pane(self):
        # round four LOW 2: mv() already pixel-clamps the top to mn (80px at sum=2000), so nT/sum is the exact on-screen
        # fraction; persisting a fixed 0.05/0.95 fraction clamp instead drifts from the pixel minimum above a 1600px pane.
        o = self.out["ratioDrift"]
        self.assertEqual(o["topFlex"], "80 1 0", "the drag clamps the on-screen top to the 80px pixel minimum: %r" % o)
        self.assertAlmostEqual(o["ratio"], 0.04, delta=0.0005,
                               msg="the persisted ratio is the on-screen 80/2000=0.04, not a 0.05 fraction clamp: %r" % o)
        self.assertLess(o["ratio"], 0.05, "above a 1600px pane the old fixed-fraction clamp drifted 20px from the screen: %r" % o)

    def test_a_column_closed_for_emptiness_tells_the_first_column_which_ids_are_on_their_way_home(self):
        # the kernel may still list a member closed from its own cross for a push or two, and the first column would draw
        # its tab until then (review find 2026-09-11): the CROSSED ids ride ahead of the store write, so the first column's
        # page holds them back (closingTabs) until the kernel's strip omits them. Only those: the backstop behind that hold
        # toasts "Couldn't close", right for a refused cross and wrong for anything else — a hold over a session the kernel
        # still listed hid the tab for fifteen seconds and toasted a close nobody asked for (the vanishing tab, 2026-09-12)
        c = self.out["closing"]
        self.assertEqual(c["partial"], [], "a prune that leaves members posts nothing")
        a = c["all"]
        self.assertEqual(a["posted"], [{"id": "f-chat", "m": {"romp": "closing", "ids": [API]}}], "the entry's members the page reported crossed, never an id it did not hold")
        self.assertEqual(a["seq"], ["post:f-chat:closing", "set:romp-chat-cols"], "the message is queued ahead of the store write's storage event")
        self.assertEqual(a["ids"], ["f-chat"]); self.assertEqual(a["stored"], {"v": 2, "cols": []})
        for key in ("uncrossed", "emptyCross"):
            u = c[key]
            self.assertEqual(u["posted"], [], "%s: a gone id nobody crossed is not held — the first column shows it the moment its strip repaints" % key)
            self.assertEqual(u["ids"], ["f-chat"], "%s: the column still closes" % key); self.assertEqual(u["stored"], {"v": 2, "cols": []})

    def test_orphaned_state_is_handed_to_the_column_that_shows_the_session_when_its_page_can_hear_it(self):
        # a v1 column's blob held drafts for many sessions and the migration keeps one (review find 2026-09-11): the page
        # offers the rest, each is taken from it and handed to its owner's page — the first column, or a later one
        o = self.out["orphan"]
        self.assertEqual(o["stored"], {"v": 2, "cols": [{"n": 2, "ids": [WEB]}, {"n": 3, "ids": [TESTS]}]})
        self.assertEqual(o["taken"], [["f-chat-2", API, True], ["f-chat-2", TESTS, True]], "taken from the offering page for the sids it does not show; its own member and junk are skipped")
        self.assertEqual(o["posted"], [{"id": "f-chat", "m": {"romp": "adopt", "sid": API, "state": {"draft": "b", "citations": [], "files": [], "staged": []}}},
                                       {"id": "f-chat-3", "m": {"romp": "adopt", "sid": TESTS, "state": {"draft": "t", "citations": [], "files": [], "staged": []}}}],
                         "each lands in the column that shows the session")
        self.assertEqual(o["left"], [WEB], "the page keeps what it shows")
        u = o["unloaded"]
        self.assertEqual(u["taken"], [], "a target whose page has not evaluated cannot hear an adopt: nothing is taken, the offer repeats on the next render")
        self.assertEqual(u["posted"], []); self.assertEqual(u["left"], [API])
        self.assertEqual(o["unknown"], 0, "an offer from no chat column changes nothing")

    def test_a_closing_column_hands_its_width_to_the_column_on_its_left_before_its_key_goes(self):
        # the halving's twin (review find 2026-09-11: with only the key deleted, the freed pixels went to every pane by
        # weight, and a tab dragged out and back narrowed the chat by a third each round trip)
        s = self.out["shrink"]
        self.assertEqual(s["third"], [["chat-pane-2", "chat-pane-3"]], "column 3's pixels go to column 2, its left neighbour")
        self.assertEqual(s["unregister"], ["chat-pane-3"])
        self.assertEqual(s["seq"], ["shrink:chat-pane-3", "unregister:chat-pane-3"], "measured while the pane is still registered and in the row, then the key goes")
        self.assertEqual(s["second"], [["chat-pane", "chat-pane-2"]], "the first later column's pixels go to the first column")

    def test_the_phone_never_splits_and_filters_nothing(self):
        m = self.out["mobile"]
        self.assertEqual(m["ids"], ["f-chat"])
        self.assertIsNone(m["sets"], "null sets: the one chat shows everything")
        self.assertIsNone(m["moved"])
        self.assertEqual(m["notify"], [["warn", "The phone shows one pane at a time, no split here."]])
        self.assertFalse(m["canSplit"])
        self.assertEqual(m["order"], ["chat-pane", "gv-a", "fleet-pane", "gv-b", "feed-pane"])
        self.assertEqual(m["stored"], m["storedWas"], "the desktop's arrangement stays in the store")
        self.assertEqual(m["saves"], 0)
        self.assertEqual(m["target"], "f-chat")


# ── THE DRAG, RUN: the zones a tab drag mounts, the rectangle, the cue, the drops ─────────────────────────────────
DRAG_DRIVER = r"""
const out = {};
const WEB = '11111111-2222-3333-4444-555555555501', API = '11111111-2222-3333-4444-555555555502', TESTS = '11111111-2222-3333-4444-555555555503', X = '11111111-2222-3333-4444-555555555509';
const EV = () => { const ev = { prevented: false, dataTransfer: {}, relatedTarget: null, preventDefault() { ev.prevented = true; }, stopPropagation() {} }; return ev; };
const isZone = (c) => c.className.split(' ').includes('col-drop');
const isEdge = (c) => c.className.split(' ').includes('col-drop-edge');
const paneIds = () => ['chat-pane'].concat(window.__rompChatFrameIds().filter((f) => f !== 'f-chat').map(window.__rompChatPaneOf));
function zonesOf(pid) { const p = BYID[pid]; return p ? p.children.filter(isZone).map((z) => ({ cls: z.className, col: z.getAttribute('data-col'), refused: z.getAttribute('data-refused'), width: z.style.width || '', top: z.style.top || '' })) : null; }
function zoneIn(pid, edge) { return (BYID[pid] ? BYID[pid].children : []).find((c) => isZone(c) && isEdge(c) === !!edge) || null; }
const isBottomZone = (c) => c.className.split(' ').includes('col-drop-bottom');
function bottomZoneIn(pid) { return (BYID[pid] ? BYID[pid].children : []).find((c) => isZone(c) && isBottomZone(c)) || null; }
function allZones() { const o = {}; paneIds().forEach((pid) => { o[pid] = zonesOf(pid); }); return o; }
function ghost() { const g = BYID['col-ghost']; return { cls: g.className, text: g.textContent, top: g.style.top || '', height: g.style.height || '', left: g.style.left || '', width: g.style.width || '' }; }
// the panes side by side, w px each behind 7 px gutters, in a row 800 px tall starting 30 px down
function rects(w) { w = w || 400; let x = 0; paneIds().forEach((pid) => { const p = BYID[pid]; if (p) { p._rect = { left: x, top: 30, width: w, height: 800 }; x += w + 7; } }); }
function on(sid, name, fromFid, stripH) { msg({ romp: 'tabDrag', on: true, sid, name, stripH: stripH === undefined ? 38 : stripH }, fromFid); }
function off() { msg({ romp: 'tabDrag', on: false }); }
function fire(z, kind, extra) { const ev = Object.assign(EV(), extra || {}); z.fire(kind, ev); return ev; }
// A) from the FIRST column with columns 2 and 3 open: a column zone on panes 2 and 3, the edge on pane 3 from its top, none on pane 1
boot({}, false);
window.__rompMoveTab(API, 'new'); window.__rompMoveTab(TESTS, 'new'); rects();
BYID['f-chat']._tabs = [{}];   // col 1 now holds only WEB (API and TESTS left): a lone source, so no split-down band on its own pane (colSize(1)===1)
on(WEB, 'web', 'f-chat');
out.fromFirst = { zones: allZones(), ghost: ghost() };
// the cue: .over on the column zone under the pointer alone; a leave whose relatedTarget is inside the zone is not a leave; a leave clears
const z2 = zoneIn('chat-pane-2', false), z3 = zoneIn('chat-pane-3', false), e3 = zoneIn('chat-pane-3', true);
const enter2 = fire(z2, 'dragenter');
out.overOne = { prevented: enter2.prevented, z2: z2.className, z3: z3.className, ghost: ghost() };
const over2 = fire(z2, 'dragover'); out.overOne.dropEffect = over2.dataTransfer.dropEffect; out.overOne.overPrevented = over2.prevented;
fire(z2, 'dragleave', { relatedTarget: z2 }); out.overOne.stillOver = z2.className;
fire(z2, 'dragleave'); out.overOne.afterLeave = z2.className;
// the edge: the rectangle at the right half of the rightmost pane, the row's height, the name as its line; the leave hides it
fire(e3, 'dragenter'); out.edgeCue = { ghost: ghost(), z3: z3.className, paneRect: BYID['chat-pane-3']._rect };
fire(e3, 'dragleave'); out.edgeCue.afterLeave = ghost();
// the drop on the edge: a new column holding the dragged session, everything unmounted; the page's dragend after it has nothing left to do
CALLS.notify = [];
fire(e3, 'dragenter'); const dropEv = fire(e3, 'drop');
out.dropEdge = { prevented: dropEv.prevented, ids: ids(), stored: cols(), zones: allZones(), ghost: ghost(), notify: CALLS.notify.slice(), blob4: blob(4), targetWeb: tgt(WEB) };
off(); out.dropEdge.afterOff = { zones: allZones(), ghost: ghost() };
// B) from the RIGHTMOST column (3, holding two): the edge sits on pane 3 under its strip and pane 3 gets no column zone; off unmounts; a second on re-mounts cleanly
boot({}, false);
window.__rompMoveTab(API, 'new'); window.__rompMoveTab(TESTS, 'new'); window.__rompMoveTab(X, 3); rects();
on(TESTS, 'tests', 'f-chat-3', 44);
out.fromLast = { zones: allZones() };
off(); out.fromLast.afterOff = { zones: allZones(), ghost: ghost() };
on(TESTS, 'tests', 'f-chat-3', 44); on(TESTS, 'tests', 'f-chat-3', 44);
out.fromLast.remounted = allZones(); off();
// C) from a later column holding ONLY the dragged session: no edge zone anywhere (a new column would twin the origin); a drop on pane 3's zone moves it there and the emptied origin closes
boot({}, false);
window.__rompMoveTab(API, 'new'); window.__rompMoveTab(TESTS, 'new'); rects();
on(API, 'api', 'f-chat-2');
out.alone = { zones: allZones() };
fire(zoneIn('chat-pane-3', false), 'drop');
out.alone.dropped = { ids: ids(), stored: cols(), zones: allZones() };
// D) a drop on the FIRST column's zone: home (the first column derives); the origin keeps its other member
boot({}, false);
window.__rompMoveTab(API, 'new'); window.__rompMoveTab(TESTS, 2); rects();
on(API, 'api', 'f-chat-2');
fire(zoneIn('chat-pane', false), 'dragenter'); out.home = { over: zoneIn('chat-pane', false).className, zones: allZones() };
fire(zoneIn('chat-pane', false), 'drop');
out.home.dropped = { ids: ids(), stored: cols(), zones: allZones(), targetApi: tgt(API) };
// E) from the first column onto column 2's zone (pane 2 is also the rightmost: it carries both zones, the edge from its top)
boot({}, false);
window.__rompMoveTab(API, 'new'); rects();
on(WEB, 'web', 'f-chat');
out.into2 = { zones: allZones() };
fire(zoneIn('chat-pane-2', false), 'drop');
out.into2.dropped = { ids: ids(), stored: cols(), zones: allZones() };
// F) at the CAP: the edge is mounted refused; the rectangle wears .refused and says so; a drop notifies and changes nothing
boot({}, false);
window.__rompMoveTab(WEB, 'new'); window.__rompMoveTab(API, 'new'); window.__rompMoveTab(TESTS, 'new'); rects();
on(X, 'x', 'f-chat');
const e4 = zoneIn('chat-pane-4', true);
out.cap = { zones: allZones(), refused: e4 && e4.getAttribute('data-refused') };
fire(e4, 'dragenter'); out.cap.ghost = ghost();
CALLS.notify = []; CALLS.sets = [];
fire(e4, 'drop');
out.cap.dropped = { ids: ids(), stored: cols(), notify: CALLS.notify.slice(), saves: saves(), zones: allZones(), ghost: ghost() };
// G) the geometry: the edge a fifth of the pane, 72 to 180 px; the rectangle the pane's right half at the row's height
boot({}, false); window.__rompMoveTab(API, 'new');
out.geometry = {};
[200, 400, 1000].forEach((w) => { rects(w); on(WEB, 'web', 'f-chat'); const e = zoneIn('chat-pane-2', true); fire(e, 'dragenter');
  out.geometry[w] = { edgeWidth: e.style.width, edgeTop: e.style.top, ghost: ghost(), paneLeft: BYID['chat-pane-2']._rect.left }; off(); });
// H) one column: the first is the source AND the rightmost — the edge alone, under its strip; a drop opens column 2
boot({}, false); rects();
on(WEB, 'web', 'f-chat', 38);
out.single = { zones: allZones() };
fire(zoneIn('chat-pane', true), 'drop');
out.single.dropped = { ids: ids(), stored: cols() };
// I) the phone mounts nothing; a message from no chat column, or with no sid, mounts nothing
boot({}, true);
on(WEB, 'web', 'f-chat');
out.phone = { zones: zonesOf('chat-pane'), body: Array.from(BODY_CLASSES).sort() };
boot({}, false); rects();
msg({ romp: 'tabDrag', on: true, sid: WEB, name: 'web', stripH: 38 });
out.unknown = { zones: zonesOf('chat-pane') };
on('', 'web', 'f-chat'); out.unknown.noSid = zonesOf('chat-pane');
// J) a DOWN split of a later column leaves the right-edge zone mounted: lastPane must skip the bottom pane (which has
// no chat-pane-<n> element), else mountZones' if(!p)return short-circuits before the edge zone
boot({}, false);
window.__rompMoveTab(API, 'new'); window.__rompMoveTab(TESTS, 2); rects();   // col 2 = [API, TESTS]
window.__rompMoveTab(TESTS, 'down'); rects();                                 // split col 2: TESTS to col 2's bottom pane
on(WEB, 'web', 'f-chat');                                                     // drag from col 1
out.downSplitLast = { edgeOn2: !!zoneIn('chat-pane-2', true), stored: cols(), zones: allZones() };
off();
// K) a DROP on a column's BOTTOM zone splits that column, the dragged tab to its new bottom pane; a cross-column
// split-down that empties the SOURCE side column closes it (never the target)
boot({}, false);
window.__rompMoveTab(API, 'new'); rects();   // col 1 = [WEB, TESTS], col 2 = [API] (alone)
on(API, 'api', 'f-chat-2');                  // drag API from col 2
const bz1 = bottomZoneIn('chat-pane');
CALLS.notify = [];
out.bottomDrop = { bzCol: bz1 && bz1.getAttribute('data-col') };
fire(bz1, 'dragenter'); const bde = fire(bz1, 'drop');
out.bottomDrop.prevented = bde.prevented;
out.bottomDrop.ids = ids(); out.bottomDrop.stored = cols(); out.bottomDrop.targetApi = tgt(API);
out.bottomDrop.notify = CALLS.notify.slice(); out.bottomDrop.ghost = ghost();
off();
// L) round two MEDIUM: a BOTTOM-PANE source offers NO split-down band anywhere (moveTab(down) refuses "A split pane
//    cannot split again"), and a forced down-move from it refuses.
boot({ 'romp-chat-cols': JSON.stringify({ v: 2, cols: [{ n: 2, ids: [API] }, { n: 3, ids: [TESTS], place: 'below', parent: 2, ratio: 0.5 }] }) }, false); rects();
on(TESTS, 'tests', 'f-chat-3');   // drag FROM the bottom pane (f-chat-3)
var below_bands = [];
['chat-pane', 'chat-pane-2'].forEach(function(pid){ zonesOf(pid).forEach(function(z){ if(z.cls.indexOf('col-drop-bottom')>=0)below_bands.push([pid, z.col]); }); });
CALLS.notify = [];
var belowRet = window.__rompMoveTab(TESTS, 'down', 1);
out.fromBelowSrc = { bands: below_bands, ret: !!belowRet, notify: CALLS.notify.slice() };
off();
// M) round two low (a): a cross-column split-down out of a lone BUSY source refuses (pre-check), leaving no open EMPTY column
boot({ 'romp-chat-cols': JSON.stringify({ v: 2, cols: [{ n: 2, ids: [API] }] }) }, false); rects();
BUSY['f-chat-2'] = true; CALLS.notify = [];
var busyRet = window.__rompMoveTab(API, 'down', 1);   // API is alone in col 2 and busy; a split-down into col 1 would empty col 2
out.busyDown = { ret: !!busyRet, notify: CALLS.notify.slice(), stored: cols(), ids: ids() };
BUSY['f-chat-2'] = false;
// N) round two low (b): the FIRST column's only session cannot split down (would empty the top); colSize reads f-chat's tabs
boot({}, false); rects();
BYID['f-chat']._tabs = [{}];   // col 1 holds one session
CALLS.notify = [];
var firstRet = window.__rompMoveTab(WEB, 'down');   // WEB is in the first column; entry(1) is null so only colSize guards it
out.firstLone = { ret: !!firstRet, notify: CALLS.notify.slice(), stored: cols() };
// O) a lone source whose BOTTOM PANE (kid) is busy must not let its last member leave: close() would refuse on its kid
//    gate and strand the column open and EMPTY (ids:[]). The pre-check now reads the kid frame too (closeBusy), on BOTH
//    roads: the cross-column split-down and the sideways move.
var kbStore = { v: 2, cols: [{ n: 2, ids: [API] }, { n: 3, ids: [TESTS], place: 'below', parent: 2, ratio: 0.5 }] };
boot({ 'romp-chat-cols': JSON.stringify(kbStore) }, false); rects();
BUSY['f-chat-3'] = true; CALLS.notify = [];   // the KID (bottom pane) is busy; the top (API) is lone and not busy
var kdRet = window.__rompMoveTab(API, 'down', 1);   // split-down of the lone top into col 1 would empty col 2's top; close(2) hits the kid gate
out.kidBusyDown = { ret: !!kdRet, notify: CALLS.notify.slice(), stored: cols(), ids: ids() };
BUSY['f-chat-3'] = false;
boot({ 'romp-chat-cols': JSON.stringify(kbStore) }, false); rects();
BUSY['f-chat-3'] = true; CALLS.notify = [];
var ksRet = window.__rompMoveTab(API, 1);   // sideways move of the lone top to col 1 would empty col 2's top; close(2) hits the kid gate
out.kidBusySideways = { ret: !!ksRet, notify: CALLS.notify.slice(), stored: cols(), ids: ids() };
BUSY['f-chat-3'] = false;
console.log(JSON.stringify(out));
"""


class DragZonesExecute(unittest.TestCase):
    """The drag (the user 2026-09-11, who asked for a tab dragged to the right edge to make a column and onto another
    column to move it): the real _LANDING_SPLIT_JS runs against the DOM stub and the zones are driven with synthetic
    drag events, which the shell accepts because it reads nothing from dataTransfer — the dragged sid rides the page's
    tabDrag message. Synthetic only."""
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        script = HARNESS.replace("__SPLIT_JS__", json.dumps(km._LANDING_SPLIT_JS)) + DRAG_DRIVER
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(script)
            path = f.name
        try:
            r = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        finally:
            os.unlink(path)
        assert r.returncode == 0, "the drag's JS threw: " + r.stderr[:1200]
        cls.out = json.loads(r.stdout.strip().splitlines()[-1])

    @staticmethod
    def _col(col, **kw):
        return dict({"cls": "col-drop", "col": col, "refused": None, "width": "", "top": ""}, **kw)

    @staticmethod
    def _edge(top, width="80px", refused=None):
        return {"cls": "col-drop col-drop-edge", "col": None, "refused": refused, "width": width, "top": top}

    @staticmethod
    def _bottom(col, refused=None):
        # the split-down zone (PR2): one per non-split column (the source too), its height set inline, top pinned by CSS
        return {"cls": "col-drop col-drop-bottom", "col": col, "refused": refused, "width": "", "top": ""}

    def test_a_drag_from_the_first_column_mounts_a_column_zone_on_every_other_pane_and_the_edge_on_the_rightmost(self):
        o = self.out["fromFirst"]
        self.assertEqual(o["zones"], {"chat-pane": [], "chat-pane-2": [self._col("2"), self._bottom("2")],
                                      "chat-pane-3": [self._col("3"), self._edge("0px"), self._bottom("3")]},
                         "no column zone on the source, and NO split-down band on it either (col 1 is a lone source: nothing to "
                         "split off, round two MEDIUM); a whole-pane zone on the others; the edge from the rightmost pane's top, a "
                         "fifth of 400 px; and a split-down zone on every OTHER non-split column")
        self.assertEqual(o["ghost"], {"cls": "", "text": "", "top": "", "height": "", "left": "", "width": ""}, "the rectangle waits for the edge")

    def test_the_cue_marks_the_zone_under_the_pointer_alone_and_a_leave_clears_it(self):
        o = self.out["overOne"]
        self.assertTrue(o["prevented"], "dragenter is accepted (preventDefault) so the drop can land")
        self.assertEqual(o["z2"], "col-drop over", "the zone under the pointer wears .over…")
        self.assertEqual(o["z3"], "col-drop", "…alone")
        self.assertEqual(o["ghost"]["cls"], "", "a column zone never shows the rectangle")
        self.assertEqual(o["dropEffect"], "move"); self.assertTrue(o["overPrevented"])
        self.assertEqual(o["stillOver"], "col-drop over", "a crossing inside the zone's own subtree is not a leave")
        self.assertEqual(o["afterLeave"], "col-drop", "the leave clears the cue")

    def test_the_edge_shows_the_rectangle_at_the_right_half_of_the_rightmost_pane_with_the_name_as_its_line(self):
        o = self.out["edgeCue"]
        r = o["paneRect"]
        self.assertEqual(o["ghost"], {"cls": "on", "text": "web", "top": "30px", "height": "800px",
                                      "left": "%dpx" % (r["left"] + r["width"] / 2), "width": "%dpx" % (r["width"] / 2)},
                         "top and height from the row, left and width the pane's right half — what the drop produces; the session's name, no verb")
        self.assertEqual(o["z3"], "col-drop", "the column zone under the edge takes no cue of its own")
        self.assertEqual(o["afterLeave"]["cls"], "", "the leave hides the rectangle")

    def test_a_drop_on_the_edge_opens_a_new_column_on_the_session_and_unmounts_everything(self):
        o = self.out["dropEdge"]
        self.assertTrue(o["prevented"], "the drop is taken (no navigation)")
        self.assertEqual(o["ids"], ["f-chat", "f-chat-2", "f-chat-3", "f-chat-4"], "__rompMoveTab(sid, 'new'): the lowest free number")
        self.assertEqual(o["stored"], {"v": 2, "cols": [{"n": 2, "ids": [API]}, {"n": 3, "ids": [TESTS]}, {"n": 4, "ids": [WEB]}]})
        self.assertEqual(o["blob4"], {"activeId": WEB}, "the new column opens on the dragged session")
        self.assertEqual(o["targetWeb"], "f-chat-4")
        self.assertEqual(o["notify"], [])
        self.assertEqual(o["zones"], {"chat-pane": [], "chat-pane-2": [], "chat-pane-3": [], "chat-pane-4": []}, "every zone unmounted at the drop")
        self.assertEqual(o["ghost"]["cls"], "", "the rectangle hidden at the drop"); self.assertEqual(o["ghost"]["text"], "")
        self.assertEqual(o["afterOff"]["zones"], o["zones"], "the page's dragend after the drop finds nothing left to unmount")
        self.assertEqual(o["afterOff"]["ghost"]["cls"], "")

    def test_a_drag_from_the_rightmost_column_puts_the_edge_under_its_strip_and_no_column_zone_on_it(self):
        o = self.out["fromLast"]
        self.assertEqual(o["zones"], {"chat-pane": [self._col(""), self._bottom("")], "chat-pane-2": [self._col("2"), self._bottom("2")],
                                      "chat-pane-3": [self._edge("44px"), self._bottom("3")]},
                         "the first column's zone carries data-col=''; the source pane has the edge (from the strip's bottom, its strip stays "
                         "reorder territory) and its own split-down zone; every non-split column carries a split-down zone")
        self.assertEqual(o["afterOff"]["zones"], {"chat-pane": [], "chat-pane-2": [], "chat-pane-3": []}, "tabDrag off unmounts everything")
        self.assertEqual(o["afterOff"]["ghost"]["cls"], "")
        self.assertEqual(o["remounted"], o["zones"], "a second on (twice, even) re-mounts cleanly: never doubled")

    def test_a_later_column_holding_only_the_dragged_session_gets_no_edge_and_its_drop_on_another_column_closes_it(self):
        o = self.out["alone"]
        self.assertEqual(o["zones"], {"chat-pane": [self._col(""), self._bottom("")], "chat-pane-2": [],
                                      "chat-pane-3": [self._col("3"), self._bottom("3")]},
                         "no edge anywhere (a new column would twin the origin); NO band on the lone source's OWN column (col 2, "
                         "round two MEDIUM); the split-down band still rides the OTHER non-split columns (a drop there splits them "
                         "and closes the emptied origin)")
        d = o["dropped"]
        self.assertEqual(d["ids"], ["f-chat", "f-chat-3"], "__rompMoveTab(sid, 3): the emptied origin closed")
        self.assertEqual(d["stored"], {"v": 2, "cols": [{"n": 3, "ids": [TESTS, API]}]})
        self.assertEqual(d["zones"], {"chat-pane": [], "chat-pane-3": []})

    def test_a_drop_on_the_first_column_s_zone_brings_the_session_home(self):
        o = self.out["home"]
        self.assertEqual(o["over"], "col-drop over")
        d = o["dropped"]
        self.assertEqual(d["ids"], ["f-chat", "f-chat-2"], "__rompMoveTab(sid, 1): the origin keeps its other member")
        self.assertEqual(d["stored"], {"v": 2, "cols": [{"n": 2, "ids": [TESTS]}]})
        self.assertEqual(d["targetApi"], "f-chat"); self.assertEqual(d["zones"], {"chat-pane": [], "chat-pane-2": []})

    def test_the_rightmost_pane_that_is_not_the_source_carries_both_zones_and_a_drop_on_its_column_zone_moves_there(self):
        o = self.out["into2"]
        self.assertEqual(o["zones"], {"chat-pane": [self._bottom("")], "chat-pane-2": [self._col("2"), self._edge("0px"), self._bottom("2")]},
                         "the edge above the column zone (z 9 over z 8), from the top; the split-down zone below it on every non-split column")
        self.assertEqual(o["dropped"]["stored"], {"v": 2, "cols": [{"n": 2, "ids": [API, WEB]}]}, "__rompMoveTab(sid, 2)")
        self.assertEqual(o["dropped"]["ids"], ["f-chat", "f-chat-2"])

    def test_at_the_cap_the_edge_is_refused_the_rectangle_says_so_and_a_drop_changes_nothing(self):
        o = self.out["cap"]
        self.assertEqual(o["refused"], "1", "mounted with data-refused")
        self.assertEqual(o["zones"]["chat-pane-4"], [self._col("4"), self._edge("0px", refused="1"), self._bottom("4", refused="1")],
                         "at the cap the split-down zone is mounted refused too (a split adds a pane, and the cap counts panes)")
        self.assertEqual(sorted(o["ghost"]["cls"].split()), ["on", "refused"]); self.assertEqual(o["ghost"]["text"], "Four panes at most")
        d = o["dropped"]
        self.assertEqual(d["ids"], ["f-chat", "f-chat-2", "f-chat-3", "f-chat-4"], "nothing opened")
        self.assertEqual(d["stored"], {"v": 2, "cols": [{"n": 2, "ids": [WEB]}, {"n": 3, "ids": [API]}, {"n": 4, "ids": [TESTS]}]}, "nothing moved")
        self.assertEqual(d["notify"], [["warn", "Four panes at most, close one first."]], "the existing refusal, said once")
        self.assertEqual(d["saves"], 0)
        self.assertEqual(d["zones"], {"chat-pane": [], "chat-pane-2": [], "chat-pane-3": [], "chat-pane-4": []}); self.assertEqual(d["ghost"]["cls"], "")

    def test_the_geometry_is_a_fifth_of_the_pane_clamped_and_the_pane_s_right_half(self):
        g = self.out["geometry"]
        self.assertEqual(g["200"]["edgeWidth"], "72px", "the floor: 0.2 × 200 = 40 → 72")
        self.assertEqual(g["400"]["edgeWidth"], "80px", "a fifth")
        self.assertEqual(g["1000"]["edgeWidth"], "180px", "the ceiling: 0.2 × 1000 = 200 → 180")
        for w in ("200", "400", "1000"):
            self.assertEqual(g[w]["edgeTop"], "0px", "not the source: from the top")
            half = int(w) / 2
            self.assertEqual(g[w]["ghost"], {"cls": "on", "text": "web", "top": "30px", "height": "800px", "left": "%gpx" % (g[w]["paneLeft"] + half), "width": "%gpx" % half})

    def test_one_column_is_both_source_and_rightmost_so_the_edge_alone_sits_under_its_strip(self):
        o = self.out["single"]
        self.assertEqual(o["zones"], {"chat-pane": [self._edge("38px"), self._bottom("")]},
                         "stripH from the page's message; the lone column carries its own split-down zone")
        self.assertEqual(o["dropped"]["ids"], ["f-chat", "f-chat-2"]); self.assertEqual(o["dropped"]["stored"], {"v": 2, "cols": [{"n": 2, "ids": [WEB]}]})

    def test_the_phone_and_a_message_from_no_chat_column_mount_nothing(self):
        self.assertEqual(self.out["phone"], {"zones": [], "body": ["po-chat", "po-feed", "po-timeline"]}, "no zone, and no body class for the gesture (nothing read one; review find 2026-09-11)")
        self.assertEqual(self.out["unknown"], {"zones": [], "noSid": []})

    def test_a_down_split_of_the_last_column_leaves_the_right_edge_zone_mounted(self):
        o = self.out["downSplitLast"]
        # lastPane() must skip the bottom pane (no chat-pane-<n> element): the edge zone stays on the last SIDE column
        self.assertTrue(any(isinstance(c, dict) and c.get("place") == "below" and c.get("parent") == 2 for c in o["stored"]["cols"]),
                        "col 2 is split down (a place:'below' entry with parent 2): %r" % o["stored"])
        self.assertTrue(o["edgeOn2"], "the right-edge (new-column) zone is still mounted on the last side column after a down split: %r" % o["zones"])

    def test_a_drop_on_a_bottom_zone_splits_that_column_and_a_cross_column_split_closes_the_emptied_source(self):
        o = self.out["bottomDrop"]
        self.assertEqual(o["bzCol"], "", "the first column's bottom zone carries data-col=''")
        self.assertTrue(o["prevented"], "the drop is taken (no navigation)")
        # API dragged from its lone column 2 onto column 1's bottom zone: it becomes a bottom pane under column 1
        # (place:'below', parent 1), and column 2, emptied by the cross-column split-down, closes
        self.assertEqual(o["stored"], {"v": 2, "cols": [{"n": 3, "ids": [API], "place": "below", "parent": 1, "ratio": 0.5}]},
                         "API is a bottom pane under column 1; the emptied source column 2 closed")
        self.assertEqual(o["ids"], ["f-chat", "f-chat-3"], "column 2's frame closed; the new bottom pane is f-chat-3")
        self.assertEqual(o["targetApi"], "f-chat-3", "API resolves to its own bottom pane")
        self.assertEqual(o["notify"], [], "a valid split-down notifies nothing")
        self.assertEqual(o["ghost"]["cls"], "", "the rectangle is hidden at the drop")

    def test_a_bottom_pane_source_offers_no_split_down_band_and_a_forced_down_move_refuses(self):
        # round two MEDIUM: a tab already in a bottom pane cannot split again, so mountZones suppresses the band on every
        # pane (fromBelow), and moveTab(sid,'down') refuses.
        o = self.out["fromBelowSrc"]
        self.assertEqual(o["bands"], [], "no split-down band mounts anywhere for a bottom-pane source: %r" % o)
        self.assertFalse(o["ret"], "a forced down-move from a bottom pane returns null (refused)")
        self.assertEqual(o["notify"], [["warn", "A split pane cannot split again."]], "…with the reason")

    def test_a_cross_column_split_down_out_of_a_busy_lone_source_refuses_and_leaves_no_empty_column(self):
        # round two low (a): the busy pre-check refuses BEFORE the split; else the session leaves, close() refuses on the
        # busy guard, and a lone source is left open and EMPTY (ids:[]).
        o = self.out["busyDown"]
        self.assertEqual(o["notify"], [["warn", "A session is still being created in this column."]], "the busy pre-check refuses")
        self.assertEqual(o["stored"], {"v": 2, "cols": [{"n": 2, "ids": [API]}]}, "col 2 keeps its session, never emptied to ids:[]: %r" % o)
        self.assertEqual(o["ids"], ["f-chat", "f-chat-2"], "no new bottom pane, no empty column left behind")

    def test_the_first_columns_only_session_cannot_split_down_into_an_empty_top(self):
        # round two low (b): entry(1) is null, so the lone guard reads colSize(1) = the first column's own tabs; splitting
        # its only session down would leave an empty top, so it is refused.
        o = self.out["firstLone"]
        self.assertEqual(o["notify"], [["warn", "This session is already alone in its column."]], "colSize(1) sees one tab: refused")
        self.assertIsNone(o["stored"], "nothing split: the store is untouched: %r" % o)

    def test_a_lone_source_whose_bottom_pane_is_busy_refuses_a_split_down_and_leaves_no_empty_column(self):
        # a lone top whose KID (bottom pane) is busy: the split-down pre-check reads the kid frame (closeBusy), so it
        # refuses up front. Before the fix, busy(src) alone passed, the session left, and close(2) refused on the kid
        # gate, stranding col 2 open and EMPTY (ids:[]).
        o = self.out["kidBusyDown"]
        self.assertEqual(o["notify"], [["warn", "A session is still being created in this column."]], "the kid-busy pre-check refuses")
        self.assertEqual(o["stored"], {"v": 2, "cols": [{"n": 2, "ids": [API]}, {"n": 3, "ids": [TESTS], "place": "below", "parent": 2, "ratio": 0.5}]},
                         "col 2's top keeps its session; nothing emptied to ids:[]: %r" % o)
        self.assertEqual(o["ids"], ["f-chat", "f-chat-2", "f-chat-3"], "no new bottom pane opened")

    def test_a_lone_source_whose_bottom_pane_is_busy_refuses_a_sideways_move_and_leaves_no_empty_column(self):
        # the same, on the pre-existing sideways-move road: closeBusy reads the kid frame too.
        o = self.out["kidBusySideways"]
        self.assertEqual(o["notify"], [["warn", "A session is still being created in this column."]], "the kid-busy pre-check refuses")
        self.assertEqual(o["stored"], {"v": 2, "cols": [{"n": 2, "ids": [API]}, {"n": 3, "ids": [TESTS], "place": "below", "parent": 2, "ratio": 0.5}]},
                         "col 2's top keeps its session; nothing emptied to ids:[]: %r" % o)
        self.assertEqual(o["ids"], ["f-chat", "f-chat-2", "f-chat-3"], "the move refused, col 2 intact")


if __name__ == "__main__":
    unittest.main()
