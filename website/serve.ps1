# Build-then-serve wrapper for the static website (Windows version of serve.sh).
#
# Rebuilds dist/ only when needed:
#   - dist/index.html is missing, or
#   - the git HEAD changed since the last build (i.e. after `git pull`).
# Then serves dist/ via `vite preview` on port 5280.
#
#   .\serve.ps1            build-if-stale + preview on http://localhost:5280
#
$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

try { $Head = (git rev-parse HEAD 2>$null) } catch { $Head = $null }
if (-not $Head) { $Head = "no-git" }
$Stamp = "dist\.build-head"

$Stale = -not (Test-Path "dist\index.html") -or -not (Test-Path $Stamp) -or ((Get-Content $Stamp -Raw).Trim() -ne $Head)

if ($Stale) {
    Write-Host "> building website (HEAD=$Head)..."
    if (-not (Test-Path "node_modules")) {
        npm ci
    }
    npm run build
    Set-Content -Path $Stamp -Value $Head -NoNewline
} else {
    Write-Host "> dist/ is up to date (HEAD=$Head), skipping build."
}

Write-Host "> serving dist/ at http://localhost:5280 ..."
& ".\node_modules\.bin\vite.cmd" preview --host 0.0.0.0 --port 5280 --strictPort
