# Start the standalone data viewers (falkordb / rqlite / qdrant / redis)
# plus the portal entry page on :19786 — PowerShell port of serve.sh.
#
#   .\serve.ps1         sync deps if needed, then start portal + configured viewers
#
# The portal always starts; a viewer starts only when its data store is
# present in browser/.env. Ctrl+C reaps everything this script started.
#
# The viewers are an independent unit (own pyproject.toml / .env), like
# server/ — nothing here reads the desktop app's root .env.
param()

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot   # browser/ — its own uv project

$Head = git rev-parse HEAD 2>$null
if (-not $Head) { $Head = "no-git" }
$Stamp = ".venv/.sync-head"

if (-not (Test-Path .venv) -or ((Get-Content $Stamp -ErrorAction SilentlyContinue) -ne $Head)) {
    Write-Host "▶ syncing viewer dependencies (HEAD=$Head)…"
    uv sync
    Set-Content $Stamp $Head
} else {
    Write-Host "▶ venv is up to date (HEAD=$Head), skipping sync."
}

# Ask this unit's own config which viewers have a data store to browse.
$Configured = uv run python -c @"
from config import SERVICES
for name, script in (('falkordb', 'falkordb_viewer.py'),
                     ('rqlite', 'rqlite_viewer.py'),
                     ('qdrant', 'qdrant_viewer.py'),
                     ('redis', 'redis_viewer.py')):
    if SERVICES.configured(name):
        print(name, script)
"@

if (-not $Configured) {
    Write-Warning "no data store configured in browser/.env — starting the portal only."
    Write-Host "  Copy browser/.env.example to browser/.env and fill in the stores."
}

$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$Procs = @()
try {
    Write-Host "▶ starting portal (portal.py)"
    $Procs += Start-Process -FilePath $Python -ArgumentList "portal.py" `
                -WorkingDirectory $PSScriptRoot -NoNewWindow -PassThru

    foreach ($line in @($Configured)) {
        if (-not ("$line".Trim())) { continue }
        $name, $script = ("$line".Trim() -split '\s+')
        Write-Host "▶ starting $name viewer ($script)"
        $Procs += Start-Process -FilePath $Python -ArgumentList $script `
                    -WorkingDirectory $PSScriptRoot -NoNewWindow -PassThru
    }
    $PortalUrl = uv run python -c "from config import SERVICES, VIEWER_HOST; print(f'http://{VIEWER_HOST}:{SERVICES.portal_port}')"
    Write-Host "✓ portal at $PortalUrl — Ctrl+C stops everything."
    Wait-Process -InputObject $Procs
} finally {
    # Reap whatever survived a Ctrl+C / terminal close so nothing orphans.
    foreach ($p in $Procs) {
        if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    }
}
