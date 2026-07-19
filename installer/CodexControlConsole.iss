#ifndef AppVersion
  #define AppVersion "0.5.3"
#endif
#ifndef SourceDir
  #define SourceDir "..\build\console-installer\dist\Codex Console"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif
#ifndef UserDataDir
  #define UserDataDir "{localappdata}\CodexControlConsole"
#endif

[Setup]
AppId={{A96DEB57-B451-45A2-A560-B97F413D9FD3}
AppName=Codex Console
AppVersion={#AppVersion}
AppVerName=Codex Console {#AppVersion}
AppPublisher=tx74666
AppPublisherURL=https://github.com/tx74666/CodexControlConsole
AppSupportURL=https://github.com/tx74666/CodexControlConsole/issues
AppUpdatesURL=https://github.com/tx74666/CodexControlConsole/releases/latest
DefaultDirName={localappdata}\Programs\Codex Console
DefaultGroupName=Codex Console
OutputDir={#OutputDir}
OutputBaseFilename=CodexControlConsole-Setup-x64
SetupIconFile=..\pc-console-icon.ico
UninstallDisplayIcon={app}\Codex Console.exe
SetupArchitecture=x64
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=yes
UsePreviousLanguage=yes
UsePreviousAppDir=yes
DisableDirPage=no
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#AppVersion}
VersionInfoProductName=Codex Console
VersionInfoDescription=Codex Console Setup for Windows x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Codex Console"; Filename: "{app}\Codex Console.exe"; WorkingDir: "{app}"; IconFilename: "{app}\_internal\codex-resource-icon.ico"; IconIndex: 0
Name: "{group}\Uninstall Codex Console"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Codex Console"; Filename: "{app}\Codex Console.exe"; WorkingDir: "{app}"; IconFilename: "{app}\_internal\codex-resource-icon.ico"; IconIndex: 0

[Registry]
Root: HKCU; Subkey: "Software\Codex\Codex Console"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Codex\Codex Console"; ValueType: string; ValueName: "Version"; ValueData: "{#AppVersion}"

[Run]
Filename: "{app}\Codex Console.exe"; Description: "{cm:LaunchProgram,Codex Console}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{#UserDataDir}"
Type: filesandordirs; Name: "{app}\cache"
Type: filesandordirs; Name: "{app}\music"
Type: filesandordirs; Name: "{app}\temp"
Type: filesandordirs; Name: "{app}\wallpapers"
Type: files; Name: "{userstartup}\Codex-Control-Hotkey.vbs"
