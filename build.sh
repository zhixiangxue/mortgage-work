#!/usr/bin/env bash
#
# One command to build the frozen desktop app (PyInstaller onedir).
#
#   ./build.sh            build frontend + package
#   ./build.sh 0.3.0      bump the version everywhere first, then build
#   ./build.sh website    build the static website only (website/dist/)
#   ./build.sh clean      remove dist/ and build/ then exit
#
# The output lands at dist/MortgageWork/Mortgage Work.exe (Windows) or
# dist/Mortgage Work.app + dist/Mortgage-Work-<version>-macOS-<arch>.dmg
# (macOS) — <arch> is ARM64 on Apple Silicon, X64 on Intel, detected at
# build time because PyInstaller emits native machine code per platform.
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CLEAN_ONLY=0
BUMP_VERSION=""
case "${1:-}" in
  "") ;;
  clean|-clean|--clean) CLEAN_ONLY=1 ;;
  website|-website|--website)
    echo "▶ building website…"
    if [ ! -d website/node_modules ]; then
      npm ci --prefix website
    fi
    npm run build --prefix website
    echo ""
    echo "✓ Website build complete → website/dist/"
    exit 0 ;;
  *)
    # A bare version number means: bump the version everywhere first, then
    # run the normal full build — same shape rule as build.ps1.
    if [[ "$1" =~ ^v?[0-9]+(\.[0-9]+)*([-.][0-9A-Za-z.]+)?$ ]]; then
      BUMP_VERSION="${1#v}"
    else
      echo "unknown argument: $1 — usage: ./build.sh [version|website|clean]" >&2
      exit 2
    fi ;;
esac

# ── Version bump (optional) ─────────────────────────────────────────────
# Bump before anything else: if it fails, the previous dist/ is still
# intact. pyproject.toml is the single source of truth; the other carriers
# are mirrors patched in step, then the lockfiles regenerate.
if [ -n "$BUMP_VERSION" ]; then
  echo "▶ bumping version to $BUMP_VERSION…"
  bump_patch() {
    local file=$1 pattern=$2
    # Guard first: a carrier that lost its version line must fail the build,
    # not get silently skipped.
    if ! grep -Eq "$pattern" "$file"; then
      echo "version pattern not found in $file" >&2
      exit 1
    fi
    # -i.bak: the one in-place form both BSD (macOS) and GNU sed accept.
    sed -i.bak -E "s/$pattern/\1$BUMP_VERSION\2/" "$file"
    rm -f "$file.bak"
    echo "  patched $file"
  }
  bump_patch "pyproject.toml" '(version = ")[^"]+(")'
  bump_patch "installer/mortgage-work.iss" '(#define MyAppVersion ")[^"]+(")'
  bump_patch "frontend/package.json" '("version": ")[^"]+(")'
  echo "▶ regenerating uv.lock…"
  uv lock
  echo "▶ regenerating frontend/package-lock.json…"
  npm install --prefix frontend --package-lock-only --no-audit --no-fund
fi

# ── Clean ────────────────────────────────────────────────────────────────

echo "▶ cleaning previous build…"
rm -rf dist/MortgageWork "dist/Mortgage Work" "dist/Mortgage Work.app" \
  "dist/Mortgage Work.dmg" build/mortgage-work build/dmg-staging
rm -f dist/Mortgage-Work-*.dmg
if [ "$CLEAN_ONLY" = "1" ]; then
  echo "done."
  exit 0
fi

# ── Frontend ─────────────────────────────────────────────────────────────

echo "▶ building frontend…"
if [ ! -d frontend/node_modules ]; then
  npm ci --prefix frontend
fi
npm run build --prefix frontend

# ── Package ──────────────────────────────────────────────────────────────

echo "▶ running PyInstaller…"
# --noconfirm: never block on an interactive y/N prompt when a stale
# dist/ directory survives the clean step (mirrors build.ps1).
.venv/bin/python -m PyInstaller --noconfirm mortgage-work.spec

# ── DMG (macOS only) ─────────────────────────────────────────────────────
# The distribution format Mac users expect: open, drag to Applications.
# hdiutil ships with macOS — no extra tooling. The Applications symlink
# makes the drag target visible inside the mounted volume. Unsigned for
# now, so first launch needs right-click → Open (Gatekeeper quarantine).

# Emit one artifact line in copy-paste shape for the admin release form
# (url / sha256 / size). The human size is a sanity check, the byte
# count is what goes into the form.
print_artifact() {
  local file=$1 platform=$2
  local sha size hr
  sha=$(shasum -a 256 "$file" | awk '{print $1}')
  size=$(stat -f%z "$file")
  hr=$(du -h "$file" | awk '{print $1}')
  echo ""
  echo "── release info (${platform}) ─────────────────────────────"
  echo "  file:      $(basename "$file")  (${hr})"
  echo "  url:       <paste the download URL after uploading>"
  echo "  sha256:    ${sha}"
  echo "  size:      ${size}"
  echo "──────────────────────────────────────────────────────────"
}

if [[ "$(uname)" == "Darwin" ]]; then
  echo "▶ creating DMG…"
  # Version stamp in the filename, same convention as the Windows Setup
  # exe — pyproject.toml is the single source. A DMG without a version is
  # a mystery file in a Downloads folder.
  app_version=$(.venv/bin/python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
  # Architecture label follows the *build machine*, never hardcoded: an app
  # built on Intel won't run natively on Apple Silicon and vice versa, so
  # the filename must tell users which one they downloaded. uname -m
  # reports arm64 on M-series chips, x86_64 on Intel.
  case "$(uname -m)" in
    arm64)  arch_label="ARM64"; platform_id="macos-arm64" ;;
    x86_64) arch_label="X64";   platform_id="macos-x64" ;;
    *)      arch_label="$(uname -m)"; platform_id="" ;;
  esac
  dmg="dist/Mortgage-Work-${app_version}-macOS-${arch_label}.dmg"
  staging="build/dmg-staging"
  rm -rf "$staging"
  mkdir -p "$staging"
  cp -R "dist/Mortgage Work.app" "$staging/"
  ln -s /Applications "$staging/Applications"
  rm -f "$dmg"
  hdiutil create -volname "Mortgage Work" -srcdir "$staging" \
    -ov -format UDZO "$dmg" >/dev/null
  rm -rf "$staging"
  echo ""
  echo "✓ Build complete → dist/Mortgage Work.app + $dmg"
  echo ""
  echo "version:     ${app_version}"
  print_artifact "$dmg" "$platform_id"
else
  echo ""
  echo "✓ Build complete → dist/Mortgage Work.app"
fi
