#!/usr/bin/env python3
"""The mobile shell's composer padding is load-bearing for the send button's position (2026-07-29).

The Send and Attach buttons are absolutely positioned inside #composer, so their `right` offsets are
measured from ITS padding edge. The kernel's mobile CSS narrows that padding from 24px to 10px, and
styles.css carries a second set of offsets under the SAME media query to match. Change the padding here
and the buttons move relative to the box they are supposed to sit inside — which is exactly the class of
breakage this pins, since the two live in different files and the coupling is otherwise invisible.

(A landscape iPad is a coarse pointer WIDER than 1024, so it keeps the desktop padding: that is why the
query carries a max-width at all, and why the offsets cannot simply live in the coarse block.)
"""
import os
import re
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ.setdefault("XDG_STATE_HOME", tempfile.mkdtemp())
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel_mcomp", os.path.join(BIN, "romp-kernel")).load_module()
STYLES = open(os.path.join(os.path.dirname(HERE), "ui", "webview", "styles.css")).read()


class MobileComposerPadding(unittest.TestCase):
    def test_the_mobile_shell_narrows_the_composer_padding_to_10px(self):
        self.assertIn("#composer{padding:8px 10px 6px}", km._CHAT_MOBILE_CSS)

    def test_it_is_scoped_to_coarse_pointers_up_to_1024px(self):
        self.assertIn("@media (pointer:coarse) and (max-width:1024px)", km._CHAT_MOBILE_CSS)

    def test_the_button_offsets_carry_a_matching_query(self):
        self.assertIn("@media (pointer: coarse) and (max-width: 1024px) {", STYLES)
        block = STYLES.split("@media (pointer: coarse) and (max-width: 1024px) {")[1].split("}")[0]
        self.assertIn("right: 14px", block, "send sits 4px inside the narrowed 10px padding")

    def test_the_offsets_keep_both_buttons_inside_the_box_at_both_paddings(self):
        """Arithmetic, so a future nudge to one number cannot quietly overlap the two buttons."""
        def px(pattern, where=STYLES):
            m = re.search(pattern, where)
            self.assertIsNotNone(m, "missing rule: %s" % pattern)
            return int(m.group(1))

        coarse = STYLES[STYLES.index("/* TOUCH (the user 2026-07-29"):]
        narrow = STYLES.split("@media (pointer: coarse) and (max-width: 1024px) {")[1].split("\n}")[0]
        send_w = px(r"#composer-send \{ right: 28px; width: (\d+)px", coarse)
        att_w = px(r"#composer-attach \{ right: 136px; width: (\d+)px", coarse)
        for label, send_right, att_right, pad in (
                ("wide (iPad landscape, 24px padding)", 28, 136, 24),
                ("narrow (mobile shell, 10px padding)", px(r"#composer-send \{ right: (\d+)px; \}", narrow),
                 px(r"#composer-attach \{ right: (\d+)px; \}", narrow), 10)):
            with self.subTest(label):
                self.assertGreaterEqual(send_right, pad, "send would hang outside the box's right edge")
                self.assertGreaterEqual(att_right, send_right + send_w,
                                        "the paperclip would overlap the send button")
                self.assertGreaterEqual(att_right, pad)
                # and neither is so far left that it lands under the text's own inset
                self.assertLess(att_right + att_w, 400, "the pair would eat a phone's whole box width")


if __name__ == "__main__":
    unittest.main()
