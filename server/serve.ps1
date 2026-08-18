# Sync-then-serve wrapper for the auth service (Windows counterpart of serve.sh).
#
# Syncs the venv only when needed:
#   - .venv is missing, or
#   - the git HEAD changed since the last sync (i.e. after `git pull`).
# Then runs the app in-process so the caller (service wrapper / terminal)
# manages the real process.
#
# Requires uv on the box:
#   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

$ErrorActionPreference = "Stop"

Set-Location (Split-Path -Parent $PSScriptRoot)   # repo root

$HEAD = & git rev-parse HEAD 2>$null
if ($LASTEXITCODE -ne 0) { $HEAD = "no-git" }
$STAMP = ".venv\.sync-head"

$stamped = $null
if (Test-Path $STAMP) { $stamped = (Get-Content $STAMP -Raw).Trim() }

if (-not (Test-Path .venv) -or ($stamped -ne $HEAD)) {
  Write-Host ">> syncing dependencies (HEAD=$HEAD)..."
  & uv sync
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  Set-Content -Path $STAMP -Value $HEAD -NoNewline
} else {
  Write-Host ">> venv is up to date (HEAD=$HEAD), skipping sync."
}

# main.py reads its own server/.env (bind address, SMTP, provisioning and
# client-entitlement keys). uvicorn binds AUTH_HOST:AUTH_PORT from that file.
& uv run python server/main.py
exit $LASTEXITCODE
