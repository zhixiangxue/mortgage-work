; Inno Setup script for Mortgage Work (Windows installer).
;
; Compiled by build.ps1 (and the CI workflow) after PyInstaller finishes:
;   iscc installer\mortgage-work.iss
;   → dist/Mortgage-Work-<version>-Setup.exe
;
; Per-user install ({localappdata}\Programs) by default — no UAC prompt.
; The admin option stays available via PrivilegesRequiredOverridesAllowed.

#define MyAppName "Mortgage Work"
; Version is injected by build.ps1 / CI from pyproject.toml via
; /DMyAppVersion=x.y.z; the literal below is only used when compiling
; the script by hand and must stay in sync as a fallback.
#ifndef MyAppVersion
  #define MyAppVersion "0.2.0"
#endif
#define MyAppPublisher "Mortgage Work"
#define MyAppExeName "Mortgage Work.exe"

[Setup]
; "x64compatible" requires Inno Setup 6.3+ (what winget installs today).
ArchitecturesInstallIn64BitMode=x64compatible
AppId={{7D2E6A41-5B8C-4B2E-9A31-2C4F8E1D9B05}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\MortgageWork
DefaultGroupName={#MyAppName}
; Whole onedir tree — no per-file listing needed.
SourceDir=..
OutputDir=dist
OutputBaseFilename=Mortgage-Work-{#MyAppVersion}-Setup
SetupIconFile=assets\icon.ico
; Desktop shortcut is opt-in at install time.
AllowNoIcons=yes
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; Close a running app so files aren't locked during upgrade.
CloseApplications=yes
RestartApplications=no
; Per-user needs no elevation; allow admin mode when the user picks it.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\MortgageWork\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
