# One command to build the frozen desktop app (PyInstaller onedir).
#
#   .\build.ps1            build frontend + package + installer
#   .\build.ps1 website    build the static website only (website/dist/)
#   .\build.ps1 clean      remove dist/ and build/ then exit
#
# The output lands at dist/MortgageWork/Mortgage Work.exe plus the
# installer dist/Mortgage-Work-<version>-Setup.exe.
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
# Kill leftovers from previous builds or smoke tests: the worker subprocess
# survives a Kill() of the main exe (start_new_session) and keeps file
# handles open — PyInstaller's COLLECT then dies with "拒绝访问".
Get-Process | Where-Object {
    $_.Name -eq "Mortgage Work" -and $_.Path -and $_.Path.StartsWith("$PWD\dist")
} | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
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
Get-ChildItem dist -Filter "Mortgage-Work-*-Setup.exe" -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue
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

# ── Bundled MinGit ─────────────────────────────────────────────────────
# End users must not install git: the frozen package ships MinGit inside.
# Download happens here (build time only, never at runtime), and gets
# trimmed down — we only need non-interactive https clone/fetch/pull/push,
# so the msys shell (usr/), Git Credential Manager (.NET/Avalonia) and
# scalar are dead weight (~65 MB).
$MingitVersion = "2.47.1"
$MingitZipName = "MinGit-$MingitVersion-64-bit.zip"
$MingitUrl     = "https://github.com/git-for-windows/git/releases/download/v$MingitVersion.windows.1/$MingitZipName"
$MingitDir     = Join-Path $PSScriptRoot "vendor\mingit"

Write-Host "> ensuring bundled MinGit..."
if (-not (Test-Path (Join-Path $MingitDir "cmd\git.exe"))) {
    $MingitZip = Join-Path $env:TEMP $MingitZipName
    Write-Host "  downloading $MingitUrl"
    Invoke-WebRequest -Uri $MingitUrl -OutFile $MingitZip -UseBasicParsing
    if (Test-Path $MingitDir) { Remove-Item -Recurse -Force $MingitDir }
    Expand-Archive -Path $MingitZip -DestinationPath $MingitDir -Force
    Remove-Item $MingitZip -ErrorAction SilentlyContinue
}
# Trim non-essential files (idempotent — also covers hand-extracted trees).
$MingitVictims = @(
    'usr', 'doc',
    'mingw64\share',
    'mingw64\etc\git-for-windows',
    'mingw64\lib\git-credential-manager',
    'mingw64\bin\scalar.exe', 'mingw64\bin\tig.exe',
    'mingw64\bin\blocked-file-util.exe', 'mingw64\bin\proxy-lookup.exe',
    'mingw64\bin\headless-git.exe',
    'mingw64\bin\git-askpass.exe', 'mingw64\bin\git-askyesno.exe',
    'mingw64\bin\git-credential-helper-selector.exe',
    'mingw64\bin\git-credential-manager.exe',
    'mingw64\bin\git-credential-manager.exe.config',
    'mingw64\bin\git-update-git-for-windows',
    'mingw64\bin\brotli.exe', 'mingw64\bin\psl.exe',
    'mingw64\bin\psl-make-dafsa', 'mingw64\bin\psl.exe.config',
    'mingw64\bin\c_rehash', 'mingw64\bin\pcre2-config'
)
foreach ($v in $MingitVictims) {
    $p = Join-Path $MingitDir $v
    if (Test-Path $p) { Remove-Item -Recurse -Force $p }
}
# .NET assemblies shipped for GCM — keep only real C runtime libs.
Get-ChildItem (Join-Path $MingitDir 'mingw64\bin') -File |
    Where-Object { $_.Name -match '^(Avalonia|MicroCom|SkiaSharp|HarfBuzzSharp|System\.|Microsoft\.|gcmcore|Atlassian\.|GitHub\.|GitLab\.)' } |
    Remove-Item -Force
# Sanitize etc/gitconfig: stock MinGit ships credential.helper=manager (we
# just deleted GCM above — leaving it makes every auth'd request crash with
# rc 128 after success) and [include]s of C:/Program Files/Git system config
# (host Git may re-inject GCM). Rewrite a hermetic config instead.
$MingitGitconfig = Join-Path $MingitDir 'etc\gitconfig'
Set-Content -Path $MingitGitconfig -Encoding ASCII -Value @"
[core]
    symlinks = false
    autocrlf = true
[color]
    interactive = true
    ui = auto
[pack]
    packSizeLimit = 2g
[help]
    format = html
[diff "astextplain"]
    textconv = astextplain
[rebase]
    autosquash = true
"@
if (-not (Test-Path (Join-Path $MingitDir "cmd\git.exe"))) {
    Write-Error "vendor\mingit\cmd\git.exe missing — MinGit bootstrap failed"
    exit 1
}
& (Join-Path $MingitDir "cmd\git.exe") --version

# ── Package ──────────────────────────────────────────────────────────────

Write-Host "> running PyInstaller..."
# --noconfirm: never block on an interactive y/N prompt when a stale
# dist/ directory survives the clean step (e.g. exe still running).
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm mortgage-work.spec

# ── Installer (Inno Setup) ───────────────────────────────────────────────
# The distribution format Windows users expect: double-click, next-next-
# finish, Start Menu shortcut, proper uninstaller. Mirrors the DMG step
# in build.sh. iscc.exe is bootstrapped here (build time only): reuse an
# existing install, else winget-install into the default location.

Write-Host "> creating installer..."
$IscriptCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    # winget installs per-user here when run without elevation.
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
$Iscript = $IscriptCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Iscript) {
    Write-Host "  Inno Setup not found — installing via winget..."
    winget install --id JRSoftware.InnoSetup -e --silent --accept-package-agreements --accept-source-agreements
    $Iscript = $IscriptCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $Iscript) {
    Write-Error "ISCC.exe not found — install Inno Setup 6 (winget install JRSoftware.InnoSetup) and rerun"
    exit 1
}
# Version comes from pyproject.toml (single source of truth) — injected
# into the .iss via /D so the Setup exe filename always matches releases.
$AppVersion = (& .\.venv\Scripts\python.exe -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])").Trim()
& $Iscript "/DMyAppVersion=$AppVersion" "installer\mortgage-work.iss"
$SetupExe = Get-ChildItem dist -Filter "Mortgage-Work-*-Setup.exe" | Select-Object -First 1
if (-not $SetupExe) {
    Write-Error "installer compile reported success but no Setup exe exists in dist/"
    exit 1
}

Write-Host ""
Write-Host "✓ Build complete → dist/MortgageWork/ + dist/$($SetupExe.Name)"

# ── Release info ─────────────────────────────────────────────────────────
# Copy-paste block for the admin release form (url / sha256 / size).
# The human-readable size is a sanity check; the byte count goes into
# the form. "platform: windows-x64" matches the admin form field as-is.
$sha = (Get-FileHash -Algorithm SHA256 $SetupExe.FullName).Hash.ToLower()
$bytes = $SetupExe.Length
$hr = "{0:N1} MB" -f ($bytes / 1MB)
Write-Host ""
Write-Host "version:     $AppVersion"
Write-Host ""
Write-Host "── release info (windows-x64) ─────────────────────────────"
Write-Host "  file:      $($SetupExe.Name)  ($hr)"
Write-Host "  url:       <paste the download URL after uploading>"
Write-Host "  sha256:    $sha"
Write-Host "  size:      $bytes"
Write-Host "──────────────────────────────────────────────────────────"
