#!/usr/bin/env bash
#
# One command to build the frozen desktop app (PyInstaller onedir).
#
#   ./build.sh          build frontend + package
#   ./build.sh clean    remove dist/ and build/ then exit
#
# The output lands at dist/Mortgage Work/Mortgage Work.exe (Windows) or
# dist/Mortgage Work.app (macOS).
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CLEAN_ONLY=0
case "${1:-}" in
  "") ;;
  clean|-clean|--clean) CLEAN_ONLY=1 ;;
  *) echo "unknown argument: $1 — usage: ./build.sh [clean]" >&2; exit 2 ;;
esac

# ── Clean ────────────────────────────────────────────────────────────────

echo "▶ cleaning previous build…"
rm -rf dist/Mortgage\ Work dist/Mortgage\ Work.app build/mortgage-work
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
.venv/bin/python -m PyInstaller mortgage-work.spec

echo ""
echo "✓ Build complete → dist/Mortgage Work/"
