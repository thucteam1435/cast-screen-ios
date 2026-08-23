#define AppName "Cast Screen AirPlay Agent"
#define AppVersion "1.0.0"
#define AppPublisher "Cast Screen"
#define AppExeName "CastScreenAirPlayAgent.exe"

[Setup]
AppId={{B1A4E9DD-5AE0-4E17-B3E5-7E0F8CC9AB21}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\CastScreen\AirPlay Agent
DefaultGroupName=Cast Screen
OutputBaseFilename=CastScreenAirPlayAgentSetup
OutputDir=..\dist\installer
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExeName}

[Files]
Source: "..\dist\CastScreenAirPlayAgent\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "..\web\AIRPLAY_AGENT_GUIDE.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\web\AIRPLAY_AGENT_PRIVACY.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Cast Screen AirPlay Agent Guide"; Filename: "{app}\AIRPLAY_AGENT_GUIDE.md"
Name: "{autodesktop}\Cast Screen AirPlay Agent Guide"; Filename: "{app}\AIRPLAY_AGENT_GUIDE.md"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "CastScreenAirPlayAgent"; ValueData: "{app}\{#AppExeName}"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Khởi động Cast Screen AirPlay Agent"; Flags: nowait postinstall skipifsilent
Filename: "{app}\AIRPLAY_AGENT_GUIDE.md"; Description: "Mở hướng dẫn sử dụng"; Flags: postinstall shellexec skipifsilent unchecked

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
