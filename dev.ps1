# One command to run the whole dev stack on Windows: the Vite dev server
# (frontend) plus the pywebview app (app.py --dev, which also spins up the
# data-browser viewers).
#
# PowerShell port of dev.sh:
#   .\dev.ps1          stop leftovers, then start the full dev stack
#   .\dev.ps1 stop     stop leftovers only (also accepts -Stop / --stop)
#
# Startup always sweeps first because the viewers and Vite bind fixed ports —
# a crashed session would otherwise block the next one with "port in use".
param(
    [Parameter(Position = 0)][string]$Action = "",
    [switch]$Stop,
    # Catch-all so typos fail loudly instead of silently starting the stack.
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest
)

$ErrorActionPreference = "Stop"

# Normalize: `stop`, `-Stop`, `--stop` all mean stop-only. Anything else is a
# mistake — bail out rather than guess (starting the stack is not a safe default).
if ($Action -match '^(--?)?stop$') { $Stop = $true; $Action = "" }
if ($Action -or $Rest) {
    Write-Error "unknown argument(s): $Action $Rest -- usage: .\dev.ps1 [stop]"
    exit 2
}

# Always operate from the project root, regardless of where the script is called.
Set-Location $PSScriptRoot

$VitePort = 5273

function Stop-Stack {
    # Ask the single source of truth (config.py, same .env the app uses) which
    # ports the viewers listen on, so this never drifts from what got started.
    $ports = @($VitePort)
    try {
        $out = uv run python -c "from config import SERVICES as s; print(s.falkordb_viewer_port, s.rqlite_viewer_port, s.qdrant_viewer_port, s.redis_viewer_port, s.agent_port)"
        $ports += ($out.Trim() -split '\s+') | ForEach-Object { [int]$_ }
    } catch {
        Write-Warning "could not read viewer ports from config.py; sweeping defaults"
        $ports += 8787, 9090, 8789, 8790, 8791
    }

    # Orphaned app instances first — killing the parent also reaps live children.
    Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" |
        Where-Object { $_.CommandLine -match 'mortgage-work.*app\.py' } |
        ForEach-Object {
            Write-Host "killing app.py: $($_.ProcessId)"
            taskkill /PID $_.ProcessId /T /F 2>$null | Out-Null
        }

    # Then anything still holding a port (children whose parent died, old Vite).
    foreach ($port in $ports) {
        $owners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
        if ($owners) {
            foreach ($ownerPid in $owners) {
                Write-Host "killing port ${port}: $ownerPid"
                taskkill /PID $ownerPid /T /F 2>$null | Out-Null
            }
        } else {
            Write-Host "port ${port}: free"
        }
    }
}

Stop-Stack
if ($Stop) {
    Write-Host "done."
    exit 0
}

$ViteProc = $null
try {
    # First run: install frontend deps so `npm run dev` doesn't fail out of the box.
    if (-not (Test-Path "frontend\node_modules")) {
        Write-Host "> installing frontend deps (first run)..."
        Push-Location frontend
        npm install
        Pop-Location
    }

    Write-Host "> starting Vite dev server on :$VitePort..."
    # cmd /c so the npm.cmd shim gets a real parent we can kill as a tree later.
    $ViteProc = Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c", "npm run dev" `
        -WorkingDirectory (Join-Path $PSScriptRoot "frontend") `
        -NoNewWindow -PassThru

    # Wait for Vite to actually accept connections before launching the window,
    # otherwise the app loads a blank page during the dev-server cold start.
    Write-Host -NoNewline "> waiting for Vite"
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        try {
            Invoke-WebRequest -Uri "http://localhost:$VitePort" -UseBasicParsing -TimeoutSec 2 | Out-Null
            $ready = $true
            Write-Host " - ready."
            break
        } catch {
            # Bail early with a clear message if Vite died (e.g. port taken, bad config).
            if ($ViteProc.HasExited) {
                Write-Host ""
                Write-Error "Vite exited before it was ready. See the output above."
                exit 1
            }
            Write-Host -NoNewline "."
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $ready) {
        Write-Error "Vite did not become ready within 30s."
        exit 1
    }

    Write-Host "> launching app (uv run python app.py --dev)..."
    # Foreground: when the window closes, we fall through to the finally block.
    # `uv run` syncs the project venv from the lockfile automatically.
    uv run python app.py --dev
}
finally {
    # Kill the Vite server and any node/esbuild children (/T = whole tree).
    if ($ViteProc -and -not $ViteProc.HasExited) {
        taskkill /PID $ViteProc.Id /T /F 2>$null | Out-Null
    }
}
