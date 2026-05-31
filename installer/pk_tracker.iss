; Inno Setup script for PK Tracker.
;
; Builds a friendly Windows installer (PKTracker-Setup.exe) from the
; PyInstaller one-file executable. Double-click, Next -> Finish: it installs to
; the user's local app folder (no admin / UAC prompt), adds Start-menu and
; optional desktop shortcuts, and offers to launch the app.
;
; Compiled in CI by Inno Setup's ISCC.exe; see .github/workflows/build-windows.yml.

#define MyAppName "PK Tracker"
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppPublisher "PK Tracker"
#define MyAppExeName "PKTracker.exe"

[Setup]
AppId={{49A95264-2684-44CE-983C-AE4BB7780C97}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; Install per-user so no administrator rights / UAC prompt are needed.
PrivilegesRequired=lowest
DefaultDirName={autopf}\PK Tracker
DisableProgramGroupPage=yes
DisableDirPage=yes
OutputDir=..\dist
OutputBaseFilename=PKTracker-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; The app keeps running in the system tray after its window is closed, so a
; previous version can hold a lock on PKTracker.exe and make an upgrade fail with
; "DeleteFile failed; code 5 (Access is denied)". Let Inno close it via the
; Restart Manager (the [Code] section below force-closes it as a fallback), and
; don't relaunch the stale copy - a fresh one starts post-install if requested.
CloseApplications=yes
RestartApplications=no
; Branded installer + Add/Remove Programs icon (the coffee-cup + clock mark).
SetupIconFile=pktracker.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.he.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\PK Tracker"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\PK Tracker"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch PK Tracker now"; Flags: nowait postinstall skipifsilent

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  // Belt-and-suspenders: the Restart Manager (CloseApplications=yes) can miss a
  // tray-only Qt app that has no visible window, so force-close any running
  // PKTracker.exe just before files are copied. taskkill returns non-zero when
  // nothing is running; that's fine, we ignore it. ewWaitUntilTerminated ensures
  // the file handle is released before the install overwrites the executable.
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#MyAppExeName}', '',
       SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;
