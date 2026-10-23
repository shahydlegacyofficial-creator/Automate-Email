; Inno Setup script - builds a normal Windows installer around the PyInstaller exe.
;   iscc /DAppVersion=1.0.0 packaging\installer.iss

#ifndef AppVersion
  #define AppVersion "1.5.0"
#endif
#define AppName "Legacy AI Email Studio"
#define OldName "Travel Essence Email Studio"
#define AppExe "LegacyAIEmailStudio.exe"

[Setup]
AppId={{8F0E2C9A-5B1D-4C3E-9A7F-2D6B1E4C8A10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Travel Essence
DefaultDirName={autopf}\{#AppName}
DefaultGroupName=Travel Essence
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=LegacyAIEmailStudio-Setup
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

; Same AppId as before, so this upgrades the old "Travel Essence Email Studio" install in place
; (same folder, settings untouched). Remove the old exe and shortcuts it left behind.
[InstallDelete]
Type: files; Name: "{app}\TravelEssenceEmailStudio.exe"
Type: files; Name: "{group}\{#OldName}.lnk"
Type: files; Name: "{autoprograms}\{#OldName}.lnk"
Type: files; Name: "{autodesktop}\{#OldName}.lnk"

[Files]
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
