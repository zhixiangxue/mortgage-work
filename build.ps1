# One command to build the frozen desktop app (PyInstaller onedir).
#
#   .\build.ps1          build frontend + package
#   .\build.ps1 clean    remove dist/ and build/ then exit
#
# The output lands at dist/Mortgage Work/Mortgage Work.exe.
param(
    [Parameter(Position = 0)][string]$Action = "",
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest
)

$ErrorActionPreference = "Stop"

if ($Action -match '^(--?)?clean$') { $Action = "clean" }
if ($Action -and $Action -ne "clean" -or $Rest) {
    Write-Error "unknown argument(s): $Action $Rest -- usage: .\build.ps1 [clean]"
    exit 2
}
if ($Action -eq "clean") { $CleanOnly = $true } else { $CleanOnly = $false }

Set-Location $PSScriptRoot

# ── Clean ────────────────────────────────────────────────────────────────

Write-Host "> cleaning previous build..."
if (Test-Path "dist/Mortgage Work") {
    Remove-Item -Recurse -Force "dist/Mortgage Work" -ErrorAction SilentlyContinue
}
if (Test-Path "build/mortgage-work") {
    Remove-Item -Recurse -Force "build/mortgage-work" -ErrorAction SilentlyContinue
}
if ($CleanOnly) {
    Write-Host "done."
    exit 0
}

# ── Frontend ─────────────────────────────────────────────────────────────

Write-Host "> building frontend..."
Push-Location frontend
try {
    if (-not (Test-Path "node_modules")) {
        npm ci
    }
    npm run build
}
finally {
    Pop-Location
}

# ── Package ──────────────────────────────────────────────────────────────

Write-Host "> running PyInstaller..."
.\.venv\Scripts\python.exe -m PyInstaller mortgage-work.spec

Write-Host ""
Write-Host "✓ Build complete → dist/Mortgage Work/"
