#define MyAppName "Matokeo RMS"
#define MyAppPublisher "MunTech"
#define MyAppExeName "MatokeoRMS.exe"
#ifndef MyAppVersion
#define MyAppVersion "0.1.0"
#endif

[Setup]
AppId={{D4B5B1E2-8A3C-47A6-A318-4D41544F4B45}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\MunTech\Matokeo RMS
DefaultGroupName=MunTech\Matokeo RMS
DisableProgramGroupPage=yes
OutputDir=..\..\dist\installer
OutputBaseFilename=Matokeo-RMS-Setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\MatokeoRMS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Matokeo RMS"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Reset Admin Password"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--reset-admin-password"
Name: "{autodesktop}\Matokeo RMS"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
