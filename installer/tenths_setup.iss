; Tenths Installer — Inno Setup Script
; ========================================
; Creates a Windows installer for the Tenths application.
;
; Prerequisites:
;   1. Build with PyInstaller first: pyinstaller installer/tenths.spec
;   2. Output should be in dist/Tenths/
;   3. Install Inno Setup from https://jrsoftware.org/isinfo.php
;   4. Compile this script with Inno Setup Compiler
;
; Output: installer/Output/TenthsSetup.exe

#define MyAppName "Tenths"
#define MyAppVersion "0.9.0"
#define MyAppPublisher "Justin Garbiso"
#define MyAppURL "https://github.com/jgarbiso/Tenths"
#define MyAppExeName "Tenths.exe"

[Setup]
AppId={{A7B8C9D0-E1F2-3456-7890-ABCDEF123456}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=Output
OutputBaseFilename=TenthsSetup
SetupIconFile=..\assets\tenths.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupentry"; Description: "Start Tenths with Windows"; GroupDescription: "Startup:"

[Files]
; Main application files (PyInstaller output)
Source: "..\dist\Tenths\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Start with Windows (optional, based on task selection)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Tenths"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: startupentry

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Tenths"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Force-kill any running instance so files can be removed cleanly.
; A graceful shutdown (window message → wait → force) is documented as a future
; improvement but not worth the installer complexity for beta.
Filename: "taskkill"; Parameters: "/IM Tenths.exe /F"; Flags: runhidden; RunOnceId: "KillTenths"

[UninstallDelete]
; Application data created at runtime. Reports and archived telemetry live under
; Documents\iRacing\telemetry — that is iRacing's directory and is never touched.
Type: filesandordirs; Name: "{localappdata}\{#MyAppName}\logs"
Type: files; Name: "{localappdata}\{#MyAppName}\settings.json"
; Remove the app-data folder itself if it is now empty (logs gone, settings gone)
Type: dirifempty; Name: "{localappdata}\{#MyAppName}"

