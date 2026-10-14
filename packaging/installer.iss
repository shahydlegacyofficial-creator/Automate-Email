; Inno Setup script - builds a normal Windows installer around the PyInstaller exe.
;   iscc /DAppVersion=1.0.0 packaging\installer.iss

#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif
#define AppName "Travel Essence Email Studio"
#define AppExe "TravelEssenceEmailStudio.exe"

[Setup]
AppId={{8F0E2C9A-5B1D-4C3E-9A7F-2D6B1E4C8A10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Travel Essence
DefaultDirName={autopf}\{#AppName}
DefaultGroupName=Travel Essence
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=TravelEssenceEmailStudio-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
