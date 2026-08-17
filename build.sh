#!/usr/bin/env bash
#
# One command to build the frozen desktop app (PyInstaller onedir).
#
#   ./build.sh            build frontend + package
#   ./build.sh website    build the static website only (website/dist/)
#   ./build.sh clean      remove dist/ and build/ then exit
#
# The output lands at dist/MortgageWork/Mortgage Work.exe (Windows) or
# dist/Mortgage Work.app (macOS).
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CLEAN_ONLY=0
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
  *) echo "unknown argument: $1 — usage: ./build.sh [website|clean]" >&2; exit 2 ;;
esac

# ── Clean ────────────────────────────────────────────────────────────────

echo "▶ cleaning previous build…"
rm -rf dist/MortgageWork "dist/Mortgage Work" "dist/Mortgage Work.app" build/mortgage-work
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

echo ""
echo "✓ Build complete → dist/Mortgage Work.app (dist/MortgageWork/)"
