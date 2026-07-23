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
# The bump is NOT committed. package.json holds a stable base version; the
# strictly-newer number exists only in the packaged .vsix, and package.json is
# restored (even on failure) before this script returns. Committing the bump
# meant a version-churn commit per install and a package.json version that
# looked like romp's release version without being it. This number is a BUILD
# ID for editor cache-busting, not a romp version: `romp --version` is the one
# that answers "what romp am I running".
#
# Mirrors ../vscode-trackchanges/install.sh, minus the shared-engine wiring
# (romp-chat-view is standalone; esbuild bundles its deps in).
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v node >/dev/null 2>&1; then
  echo "!! node not found — skipping romp-chat-view install."
  exit 0
fi

# ROMP_EXT_PACKAGE_ONLY=1 → build + package the .vsix, install it into nothing.
# Lets CI (and tests/install-sh.bats) exercise the stamp/restore and the packaging
# without touching the editors on the machine running it.
PACKAGE_ONLY="${ROMP_EXT_PACKAGE_ONLY:-}"

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

if [ "${#CLIS[@]}" -eq 0 ] && [ -z "$PACKAGE_ONLY" ]; then
  echo "!! No VS Code-family editor CLI found — skipping install (built dist/ is ready for F5)."
  exit 0
fi

echo "==> npm install"
npm install --silent   # idempotent; ensures dev deps (esbuild, types) exist

# Set the packaged version WITHOUT committing it (see the header note for why).
# Patch = epoch seconds: monotonic by construction, so every install is strictly
# newer than the last no matter how often you reinstall at the same commit (a
# commit count would NOT be: edit -> install -> reload repeats one commit).
# major.minor stays on the committed line so a reinstall can never look like a
# DOWNGRADE to an editor holding an older build.
# `|| true` + `return 0`: this is an EXIT trap, so a non-zero last command in it can
# leak into the script's exit status and turn a clean run into a failure.
cleanup_pkg() { [ -f package.json.orig ] && mv -f package.json.orig package.json || true; return 0; }
trap cleanup_pkg EXIT INT TERM
cp package.json package.json.orig

echo "==> stamp build version"
node -e 'const fs=require("fs"),f="package.json",p=JSON.parse(fs.readFileSync(f));const v=p.version.split(".");v[2]=String(Math.floor(Date.now()/1000));p.version=v.join(".");fs.writeFileSync(f,JSON.stringify(p,null,2)+"\n");console.log("    build version -> "+p.version+" (not committed)");'

echo "==> build"
node esbuild.js

# Fixed output name (overwritten each run) so .vsix artifacts don't pile up.
echo "==> package .vsix"
npx --yes @vscode/vsce package --no-dependencies --allow-missing-repository -o romp-chat-view.vsix >/dev/null
echo "    packaged romp-chat-view.vsix"

if [ -n "$PACKAGE_ONLY" ]; then
  echo "==> ROMP_EXT_PACKAGE_ONLY set — packaged only, installed into no editor."
  exit 0
fi

# ":-" guard: bash 3.2 (the macOS system bash) treats "${arr[@]}" on an EMPTY array
# as an unbound variable under `set -u`.
for cli in "${CLIS[@]:-}"; do
  echo "==> install into: $cli"
  "$cli" --install-extension romp-chat-view.vsix --force </dev/null || echo "   (failed for $cli — continuing)"
done

echo "==> done. Reload the editor (Cmd+Shift+P -> 'Developer: Reload Window')"
echo "    or quit + reopen; the extension is then permanently active."
