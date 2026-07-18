#ifndef AppVersion
  #define AppVersion "0.4.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\build\console-installer\dist\Codex Console"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
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
SetupIconFile=..\pc-console.ico
UninstallDisplayIcon={app}\Codex Console.exe
SetupArchitecture=x64
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
Compression=lzma2/ultra64
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

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Codex Console"; Filename: "{app}\Codex Console.exe"
Name: "{autodesktop}\Codex Console"; Filename: "{app}\Codex Console.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Codex\Codex Console"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Codex\Codex Console"; ValueType: string; ValueName: "Version"; ValueData: "{#AppVersion}"

[Run]
Filename: "{app}\Codex Console.exe"; Description: "{cm:LaunchProgram,Codex Console}"; Flags: nowait postinstall skipifsilent
