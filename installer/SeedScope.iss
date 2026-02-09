#define MyAppName "SeedScope"
#define MyAppExeName "SeedScope.exe"
#define MyAppPublisher "Kevnaut"
#define MyAppURL "https://github.com/Kevnaut/SeedScope"

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{D9123D8B-A5A7-4315-B6B4-A6A681DC4BB8}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=SeedScope-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

#ifexist "..\app\assets\icon.ico"
  #define SetupIconFilePath "..\app\assets\icon.ico"
#endif
#ifndef SetupIconFilePath
  #ifexist "..\app\icon.ico"
    #define SetupIconFilePath "..\app\icon.ico"
  #endif
#endif

#ifdef SetupIconFilePath
SetupIconFile={#SetupIconFilePath}
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "..\dist\SeedScope\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
