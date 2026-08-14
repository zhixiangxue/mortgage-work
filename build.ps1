# One command to build the frozen desktop app (PyInstaller onedir).
#
#   .\build.ps1            build frontend + package
#   .\build.ps1 website    build the static website only (website/dist/)
#   .\build.ps1 clean      remove dist/ and build/ then exit
#
# The output lands at dist/MortgageWork/Mortgage Work.exe.
param(
    [Parameter(Position = 0)][string]$Action = "",
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest
)

$ErrorActionPreference = "Stop"

if ($Action -match '^(--?)?clean$') { $Action = "clean" }
if ($Action -match '^(--?)?website$') { $Action = "website" }
if ($Action -and $Action -notin "clean", "website" -or $Rest) {
    Write-Error "unknown argument(s): $Action $Rest -- usage: .\build.ps1 [website|clean]"
    exit 2
}
if ($Action -eq "clean") { $CleanOnly = $true } else { $CleanOnly = $false }

Set-Location $PSScriptRoot

# ── Website only ─────────────────────────────────────────────────────────

if ($Action -eq "website") {
    Write-Host "> building website..."
    Push-Location website
    try {
        if (-not (Test-Path "node_modules")) {
            npm ci
        }
        npm run build
    }
    finally {
        Pop-Location
    }
    Write-Host ""
    Write-Host "✓ Website build complete → website/dist/"
    exit 0
}

# ── Clean ────────────────────────────────────────────────────────────────

Write-Host "> cleaning previous build..."
if (Test-Path "dist/MortgageWork") {
    Remove-Item -Recurse -Force "dist/MortgageWork" -ErrorAction SilentlyContinue
}
# legacy spaced folder name, kept so stale builds get cleaned up too
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
# --noconfirm: never block on an interactive y/N prompt when a stale
# dist/ directory survives the clean step (e.g. exe still running).
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm mortgage-work.spec

Write-Host ""
Write-Host "✓ Build complete → dist/MortgageWork/"
