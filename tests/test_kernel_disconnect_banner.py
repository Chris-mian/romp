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
        self.assertIn('ws.onopen=function(){netState("up");', js)
        self.assertIn('ws.onclose=function(){netState("down");setTimeout(connect,1500);};', js)
        self.assertIn("ws.onerror=function(){try{ws.close();}catch(e){}};", js)
        # a RECONNECT reloads to resync, but only once the socket actually reopened (not a blind reload on close)
        self.assertIn("if(everConnected){location.reload();return;}", js)
        self.assertNotIn("ws.onclose=function(){setTimeout(function(){location.reload();},1500);};", js,
                         "the old blind-reload-on-close is gone")

    def test_timeline_boot_reports_state_and_reconnects(self):
        js = km._TIMELINE_BOOT
        self.assertIn('postMessage({romp:"wsState",app:"timeline",state:s}', js)
        self.assertIn('ws.onopen=function(){netState("up");if(everConnected){location.reload();return;}', js)
        self.assertIn('ws.onclose=function(){netState("down");setTimeout(connect,1500);};', js)
        self.assertNotIn("ws.onclose=function(){setTimeout(function(){location.reload();},1500);};", js)

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


if __name__ == "__main__":
    unittest.main()
