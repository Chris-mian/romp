"""The code panes' RENDERING, sliced out of the dashboard landing (plans/panes-as-data.md, phase one's first pin). The
registry adds guards, attribute reads and reload words to the page, so the page as a whole is not byte-identical to the
base's; what the pin holds is that with an empty registry every slice that renders the code panes is: the body tag, the
rail's pane buttons, the phone's pane tabs, the pane row's markup, the column and gutter rules, and the gutter calls.

tests/fixtures/landing-code-panes.json holds these slices as the BASE kernel rendered them, made by running this module's
`slices` over that kernel's `_landing()` with no data pane (the file names the commit). To regenerate after a deliberate
change to the shipped panes' rendering, run the same over a checkout of the new base and say so in the PR."""
import re


def slices(html):
    """The rendering slices of a landing page, {name: text}. A slice that cannot be found is the empty string, so a
    comparison against the fixture fails on the slice by name."""
    body = re.search(r"<body class='[^']*'[^>]*>", html)
    row_a, row_b = html.find("<div class=row>"), html.find("<div id=gv-ghost>")
    return {
        "body_tag": body.group(0) if body else "",
        "rail_buttons": "".join(re.findall(r"<div class=rail-btn data-pane=[^>]*>[^<]*</div>", html)),
        "phone_tabs": "".join(re.findall(r"<button data-pane=[^>]*>[^<]*</button>", html)),
        "pane_row": html[row_a:row_b] if 0 <= row_a < row_b else "",
        "column_css": "".join(r for css in re.findall(r"<style>(.*?)</style>", html, re.S)
                              for r in re.findall(r"(?<=[};])[^{};]*(?:-pane|#gv-)[^{}]*\{[^}]*\}", css)),   # the STYLE blocks only: the inline scripts name panes too
        "gutter_calls": "\n".join(re.findall(r"gutter\('gv-[a-z]',[^\n]*", html)),
    }
