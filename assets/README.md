# assets/ — brand sources

The romp mark (the swirl) and wordmark, plus the scripts that generate the
shipped raster/SVG variants:

- `make_icon.py` / `make_wordmark.py` — regenerate the icon and wordmark
  outputs (the wordmark script also refreshes the copy served at `/media` from
  `vscode-extension/media/`).
- `romp-icon-*.{svg,png}`, `romp-wordmark.png`, `swirl-*.png` — generated
  variants at the sizes the surfaces need (favicons, extension icon, loaders).
- `Anta-Regular.ttf` (+ `OFL-Anta.txt` license) — the wordmark font.
- `illustrator/` — editable design sources.

The spinning swirl glyph + wordmark + three accent-blue dots is the standard
romp loading treatment — reuse it for any new wait state (see CLAUDE.md).
