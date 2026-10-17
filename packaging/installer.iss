; Per-user installer for Sky Macro Player (no Administrator rights).
; Build: iscc /DAppVersion=3.0.0 /DSourceDir=..\dist\SkyMacroPlayer /DOutputDir=..\dist packaging\installer.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\SkyMacroPlayer"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif

[Setup]
AppId={{6F1C2B7E-3A5D-4E8B-9C21-5B7A2D9E4F10}
AppName=Sky Macro Player
AppVersion={#AppVersion}
AppPublisher=harozx
AppPublisherURL=https://github.com/harozx/macro_project
DefaultDirName={localappdata}\Programs\SkyMacroPlayer
DefaultGroupName=Sky Macro Player
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename=SkyMacroPlayer-Setup-{#AppVersion}
SetupIconFile=..\build\pyinstaller\app.ico
UninstallDisplayIcon={app}\SkyMacroPlayer.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Sky Macro Player"; Filename: "{app}\SkyMacroPlayer.exe"
Name: "{autodesktop}\Sky Macro Player"; Filename: "{app}\SkyMacroPlayer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\SkyMacroPlayer.exe"; Description: "Start Sky Macro Player"; Flags: nowait postinstall skipifsilent

; User settings, favorites, history and imported sheets live in
; %LOCALAPPDATA%\SkyMacroPlayer and are intentionally kept on uninstall.
