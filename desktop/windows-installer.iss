[Setup]
AppId={{A7229B97-45F9-4F09-950C-DF972B147632}
AppName=Duo
AppVersion=0.2.0
DefaultDirName={localappdata}\Programs\Duo
DefaultGroupName=Duo
PrivilegesRequired=lowest
OutputDir=..\release
OutputBaseFilename=Duo-Windows-x64-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\Duo.exe
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
[Files]
Source: "..\dist\Duo\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\Duo"; Filename: "{app}\Duo.exe"
Name: "{autodesktop}\Duo"; Filename: "{app}\Duo.exe"; Tasks: desktopicon
[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le bureau"; Flags: unchecked
[Run]
Filename: "{app}\Duo.exe"; Description: "Ouvrir Duo"; Flags: nowait postinstall skipifsilent
