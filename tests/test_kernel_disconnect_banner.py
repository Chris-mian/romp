"""Connection-status banner (the user 2026-06-27): a real network drop used to blind-reload each pane iframe
into a dead page, so the dashboard silently froze (the timeline "stopped moving") with no explanation. Now each
pane reports its WebSocket state to the shell, which shows ONE "Disconnected — reconnecting…" banner while any
pane is down, and the panes RECONNECT (retry) instead of blind-reloading — reloading to resync only once the
socket is actually back. Source pins on the kernel's injected JS/HTML."""
import inspect
import os
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()


class DisconnectBanner(unittest.TestCase):
    def test_pane_shim_reports_state_and_reconnects(self):
        js = km._shim("chat")
        # reports up/down to the shell
        self.assertIn('postMessage({romp:"wsState",app:APP,state:s}', js)
        self.assertIn('ws.onopen=function(){lastRecv=Date.now();netState("up");', js)   # lastRecv stamp → heartbeat watchdog
        self.assertIn('ws.onclose=function(){netState("down");', js)   # reconnects on close (wsdown loader + retry follow)
        self.assertIn("setTimeout(connect,1500);", js)
        self.assertIn("ws.onerror=function(){try{ws.close();}catch(e){}};", js)
        # a RECONNECT no longer silently reloads (the user 2026-07-05): it PROMPTS via raiseStale, and the fresh
        # socket resyncs live. The old auto-reload-on-reopen is gone.
        self.assertIn("if(wasReconn)raiseStale();", js)
        self.assertNotIn("if(everConnected){location.reload();return;}", js,
                         "the silent auto-reload-on-reconnect is replaced by a reload PROMPT")
        self.assertNotIn("ws.onclose=function(){setTimeout(function(){location.reload();},1500);};", js,
                         "the old blind-reload-on-close is gone")

    def test_shim_prompts_reload_on_reconnect_and_stale_foreground(self):
        js = km._shim("feed")
        # raiseStale routes to the shell's #rstale banner when embedded (a pane iframe), else self-injects.
        self.assertIn('window.parent.postMessage({romp:"wsStale"}', js, "embedded pane hands off to the shell banner")
        self.assertIn("function selfStale()", js, "standalone page (no shell) gets its own reload bar")
        self.assertIn("romp-stale-self", js)
        # visibility fast-path: a foregrounded tab whose socket is dead/quiet prompts at once (not after the
        # throttled 5s watchdog), and forces a reconnect to resync.
        self.assertIn('document.addEventListener("visibilitychange"', js)
        self.assertIn("Date.now()-lastRecv>STALE_MS){raiseStale();", js)

    def test_shim_reconnect_loop_cannot_die(self):
        # The retry chain used to hang entirely off onclose, and the watchdog only ever closed OPEN
        # sockets — so an attempt the browser held in CONNECTING (Firefox delays re-admitting a
        # recently-failed endpoint after a kernel restart) had NOTHING driving it forward, and the
        # "Disconnected — reconnecting…" banner sat until a manual refresh (the user 2026-07-21).
        js = km._shim("chat")
        # connect() is idempotent (one live attempt at a time) and stamps its start time
        self.assertIn("function connect(){if(ws&&(ws.readyState===0||ws.readyState===1))return;", js)
        self.assertIn("connT=Date.now();", js)
        # the watchdog handles EVERY socket state: half-open OPEN, stuck CONNECTING, and lost-timer CLOSED
        self.assertIn("if(ws.readyState===1){if(everConnected&&Date.now()-lastRecv>STALE_MS){try{ws.close();}catch(e){}}return;}", js)
        self.assertIn("if(ws.readyState===0&&Date.now()-connT>15000){try{ws.close();}catch(e){}return;}", js)
        self.assertIn("if(ws.readyState===3&&Date.now()-connT>8000){connect();}", js)
        # the foregrounding fast-path tears down a stuck CONNECTING socket too, and re-dials a closed one
        self.assertIn("if(ws&&ws.readyState<=1)ws.close();", js)
        self.assertIn("if(!ws||ws.readyState===3)connect();", js)

    def test_offline_banner_has_a_reload_button(self):
        # never dead-end (progressive disclosure rule): when the browser holds reconnects back, the
        # user's actual recovery action — reload — must be ON the banner, not a manual url-bar refresh.
        land = inspect.getsource(km._landing)
        self.assertIn("id=ro-reload", land, "the banner carries the button")
        self.assertIn("#ro-reload{", land, "and its style")
        self.assertIn("document.getElementById('ro-reload')", km._LANDING_NET_JS)
        self.assertIn("location.reload();});})();", km._LANDING_NET_JS, "a click reloads — user-initiated, never automatic")

    def test_shell_rstale_banner_shows_on_ws_stale_message(self):
        # the #rstale reload banner (formerly build-drift only) now ALSO shows on a pane's wsStale post, with a
        # connection-specific message, latched so the /version poll can't clear it out from under the user.
        self.assertIn("m.romp==='wsStale'", km._STALE_JS)
        self.assertIn("connStale=true", km._STALE_JS)
        self.assertIn("served<=loaded&&!connStale", km._STALE_JS, "the version poll must not hide a live-conn prompt")
        self.assertIn("connStale=false", km._STALE_JS, "Dismiss clears the latch")

    def test_shell_banner_words_a_build_raise_as_a_build(self):
        # a pane's build-drift raise rides the same wsStale channel tagged build:1 → the shell shows
        # BUILDMSG (not the connection wording), and latches it so its own /version poll — whose token
        # may be current — can't clear the prompt out from under the stale pane (the user 2026-07-13)
        self.assertIn("if(m.build){buildStale=true;show(BUILDMSG);}else{connStale=true;show(CONNMSG);}", km._STALE_JS)
        self.assertIn("!connStale&&!buildStale", km._STALE_JS, "the poll's clear respects both latches")
        self.assertIn("connStale=false;buildStale=false;", km._STALE_JS, "Dismiss clears both")

    def test_timeline_page_uses_the_shared_shim(self):
        # The timeline used to hand-roll its own WebSocket in _TIMELINE_BOOT (a copy of _shim's
        # connect/queue/watchdog) — which bypassed the federation manager, so remote hosts' lanes never
        # reached the pane. Now the page carries the SAME shim as every other pane (state reporting,
        # reconnect, reload-on-reopen all come from it) + the federation bundle; the boot only adapts
        # window "message" events to panel.update/applyBars and posts actions via acquireVsCodeApi.
        self.assertNotIn("new WebSocket", km._TIMELINE_BOOT, "the boot owns no socket of its own")
        page = km._timeline_page()
        self.assertIn('postMessage({romp:"wsState",app:APP,state:s}', page, "the shared shim reports state")
        self.assertIn('/ws?app=timeline', page, "the shim is instantiated for the timeline app")
        self.assertIn("/dist/federation.js", page, "the multi-kernel manager rides the page")
        self.assertIn('window.addEventListener("message"', km._TIMELINE_BOOT)
        self.assertIn("panel.update(m.data)", km._TIMELINE_BOOT)

    def test_shell_has_the_banner_and_its_listener(self):
        # the net-state script: shows the banner when ANY pane is down, clears when all are up
        self.assertIn("st[m.app]=(m.state==='up')?'up':'down'", km._LANDING_NET_JS)
        self.assertIn("bn.classList.toggle('show',down)", km._LANDING_NET_JS)
        # the shell mounts the banner element, its CSS, and wires the script
        land = inspect.getsource(km._landing)
        self.assertIn("id=romp-offline", land, "the banner element is in the shell body")
        self.assertIn("Disconnected — reconnecting…", land)
        self.assertIn("#romp-offline.show{display:flex}", land, "hidden until a pane drops")
        self.assertIn("_LANDING_NET_JS", land, "the listener script is injected into the shell")

    def test_only_visible_panes_raise_the_banner(self):
        # a pane toggled OFF still holds a live socket (the Fleet pane is hidden by default, its iframe always
        # loaded), so a blip on a pane you can't even see must NOT raise the global "Disconnected" alarm while
        # the chat pane you interact through is up (the user 2026-07-06). Gate on the pane-enabled body class
        # the toggle sets (po-chat/po-feed/po-timeline/po-fleet), and re-check when panes toggle.
        js = km._LANDING_NET_JS
        self.assertIn("function shown(k){return document.body.classList.contains('po-'+k);}", js)
        self.assertIn("if(st[k]==='down'&&shown(k))", js, "a down pane counts only while its pane is visible")
        self.assertIn("window.addEventListener('romp-panes',refresh)", js, "re-check the banner on pane toggle")
        # the pane toggle actually fires the romp-panes event this listens for, and both scripts ride the shell
        self.assertIn("new Event('romp-panes')", km._LANDING_COLLAPSE_JS)
        land = inspect.getsource(km._landing)
        self.assertIn("_LANDING_COLLAPSE_JS", land)
        self.assertIn("_LANDING_NET_JS", land)


if __name__ == "__main__":
    unittest.main()
