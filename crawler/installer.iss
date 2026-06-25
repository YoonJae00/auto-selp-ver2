; Auto-Selp Crawler Windows Installer (Inno Setup)
; Build command: iscc installer.iss
; Output: dist/AutoSelpCrawler-Setup-x.y.z.exe

#define MyAppName "Auto-Selp Crawler"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Auto-Selp"
#define MyAppExeName "AutoSelpCrawler.exe"

[Setup]
AppId={{AUTOSELP-CRAWLER-001}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\AutoSelpCrawler
DefaultGroupName=Auto-Selp
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=AutoSelpCrawler-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
DisableDirPage=no
DisableReadyPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 바로가기 만들기"; GroupDescription: "추가 옵션:"

[Files]
Source: "dist\AutoSelpCrawler\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName} 제거"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyAppName} 실행"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
