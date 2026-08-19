# One command to launch the whole local stack on Windows: the Vite dev server
# (frontend) plus the pywebview app (app.py --dev). The data-browser viewers
# are a separate standalone unit — run browser/serve.ps1 in another terminal
# if you need them.
#
# PowerShell port of launch.sh:
#   .\launch.ps1          stop leftovers, then launch the full local stack
#   .\launch.ps1 stop     stop leftovers only (also accepts -Stop / --stop)
#
# Startup always sweeps first because the agent service and Vite bind fixed
# ports — a crashed session would otherwise block the next one with "port in
# use".
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
    Write-Error "unknown argument(s): $Action $Rest -- usage: .\launch.ps1 [stop]"
    exit 2
}

# Always operate from the project root, regardless of where the script is called.
Set-Location $PSScriptRoot

$VitePort = 5273

# Every port a dev session can hold: the Vite dev server plus the agent port
# from config.py (same .env the app reads). Captured once here so Stop-Stack
# and the exit cleanup share one source of truth and neither has to spawn
# `uv run` again on the way out.
$SweepPorts = @($VitePort)
try {
    $out = uv run python -c "from config import SERVICES as s; print(s.agent_port)"
    $SweepPorts += ($out.Trim() -split '\s+') | ForEach-Object { [int]$_ }
} catch {
    Write-Warning "could not read the agent port from config.py; sweeping defaults"
    $SweepPorts += 19791
}

# Kill whatever holds a given list of ports. Process-group-agnostic, so it
# reaches servers app.py started with start_new_session=True (which on Windows
# puts each in its own process group via CREATE_NEW_PROCESS_GROUP, out of
# console Ctrl+C reach) — most importantly agent_service, which hosts the
# clerk background task. /T kills the owner's whole tree (uvicorn workers
# included), /F makes it unconditional. Shared by the startup sweep and the
# exit cleanup so the orphaned-clerk-after-Ctrl+C gap can't happen on Windows.
function Stop-PortOwners {
    param([Parameter(Mandatory)][int[]]$Ports)
    $ports = $Ports | Sort-Object -Unique
    $byPort = @{}
    try {
        Get-NetTCPConnection -LocalPort $ports -State Listen -ErrorAction SilentlyContinue |
            ForEach-Object {
                $port = [int]$_.LocalPort
                if (-not $byPort.ContainsKey($port)) { $byPort[$port] = @() }
                $byPort[$port] += [int]$_.OwningProcess
            }
    } catch {
        # Get-NetTCPConnection can throw if no listed port has a listener.
    }

    $killPids = [System.Collections.Generic.HashSet[int]]::new()
    foreach ($port in $ports) {
        $owners = @($byPort[$port] | Sort-Object -Unique)
        if ($owners.Count) {
            foreach ($ownerPid in $owners) {
                Write-Host "killing port ${port}: $ownerPid"
                [void]$killPids.Add([int]$ownerPid)
            }
        } else {
            Write-Host "port ${port}: free"
        }
    }

    $jobs = @()
    foreach ($ownerPid in $killPids) {
        $jobs += Start-Job -ArgumentList $ownerPid -ScriptBlock {
            param([int]$PidToKill)
            taskkill /PID $PidToKill /T /F 2>$null | Out-Null
        }
    }
    if ($jobs.Count) {
        Wait-Job -Job $jobs | Out-Null
        Receive-Job -Job $jobs | Out-Null
        Remove-Job -Job $jobs -Force | Out-Null
    }
}

function Stop-Stack {
    # Orphaned app instances first — killing the parent also reaps live children.
    Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" |
        Where-Object { $_.CommandLine -match 'mortgage-work.*app\.py' } |
        ForEach-Object {
            Write-Host "killing app.py: $($_.ProcessId)"
            taskkill /PID $_.ProcessId /T /F 2>$null | Out-Null
        }

    # Then anything still holding a port — $SweepPorts is built at the top.
    Stop-PortOwners -Ports $SweepPorts
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
    # Run directly (no pipeline): app.py already writes runtime.log through its
    # logging setup, and a Tee-Object pipeline swallows Ctrl+C before it reaches
    # the app, leaving Vite/agent ports behind.
    uv run python app.py --dev
}
finally {
    # Kill the Vite server and any node/esbuild children (/T = whole tree).
    if ($ViteProc -and -not $ViteProc.HasExited) {
        taskkill /PID $ViteProc.Id /T /F 2>$null | Out-Null
    }

    # Reap the detached servers by port. app.py starts the chat agent service
    # with start_new_session=True; on Windows it lands in its own process group
    # (CREATE_NEW_PROCESS_GROUP), so a console Ctrl+C never reaches it. app.py's
    # stop_services() would reap it on a clean exit, but it relies on os.killpg
    # — Unix-only — which does not apply on Windows, and its Python handler sits
    # inside pywebview's native loop anyway. Port-killing reaches agent_service
    # (and the clerk task inside it) on every exit path, however app.py died.
    Stop-PortOwners -Ports $SweepPorts
}
