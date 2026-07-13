#!/usr/bin/env bash
# Build + permanently install this extension into every VS Code-family editor
# present (VS Code, Cursor, Codium, Insiders, and any `code`/`cursor` on PATH).
# After this runs once, the extension is always loaded in normal editor windows
# — no F5 / dev host. Re-run it to pick up source changes.
#
# WHY a script (and why the version bump): editors load the INSTALLED copy under
# ~/.vscode/extensions/<publisher>.<name>-<ver>/, NOT this repo's dist/. They
# also cache extension code by version, so reinstalling the SAME version — even
# with --force — usually won't refresh on a window reload. So every install must
# be a strictly NEWER version. Rebuilding dist/ here alone changes nothing in the
# running editor; you must repackage + reinstall, which is what this does.
#
# Mirrors ../vscode-trackchanges/install.sh, minus the shared-engine wiring
# (romp-chat-view is standalone; esbuild bundles its deps in).
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v node >/dev/null 2>&1; then
  echo "!! node not found — skipping romp-chat-view install."
  exit 0
fi

# ── collect editor CLIs (dedup by resolved path) ──────────────────────
declare -a CLIS=()
add_cli() {
  local p="$1"
  [ -x "$p" ] || return 0
  local real; real="$(realpath "$p" 2>/dev/null || echo "$p")"
  for e in "${CLIS[@]:-}"; do [ "$e" = "$real" ] && return 0; done
  CLIS+=("$real")
}
# macOS app bundles
add_cli "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"
add_cli "/Applications/Cursor.app/Contents/Resources/app/bin/code"
add_cli "/Applications/VSCodium.app/Contents/Resources/app/bin/codium"
# anything on PATH (covers Linux / remote / server installs)
for c in code code-insiders cursor codium; do
  p="$(command -v "$c" 2>/dev/null || true)"; [ -n "$p" ] && add_cli "$p"
done

if [ "${#CLIS[@]}" -eq 0 ]; then
  echo "!! No VS Code-family editor CLI found — skipping install (built dist/ is ready for F5)."
  exit 0
fi

echo "==> npm install"
npm install --silent   # idempotent; ensures dev deps (esbuild, types) exist

# Bump the patch version on every install (see the header note for why).
echo "==> bump version"
node -e 'const fs=require("fs"),f="package.json",p=JSON.parse(fs.readFileSync(f));const v=p.version.split(".");v[2]=String(+v[2]+1);p.version=v.join(".");fs.writeFileSync(f,JSON.stringify(p,null,2)+"\n");console.log("    version -> "+p.version);'

echo "==> build"
node esbuild.js

# Fixed output name (overwritten each run) so .vsix artifacts don't pile up.
echo "==> package .vsix"
npx --yes @vscode/vsce package --no-dependencies --allow-missing-repository -o romp-chat-view.vsix >/dev/null
echo "    packaged romp-chat-view.vsix"

for cli in "${CLIS[@]}"; do
  echo "==> install into: $cli"
  "$cli" --install-extension romp-chat-view.vsix --force </dev/null || echo "   (failed for $cli — continuing)"
done

echo "==> done. Reload the editor (Cmd+Shift+P -> 'Developer: Reload Window')"
echo "    or quit + reopen; the extension is then permanently active."
